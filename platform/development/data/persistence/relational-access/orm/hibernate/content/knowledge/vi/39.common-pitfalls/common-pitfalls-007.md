# Gọi merge nhưng tiếp tục sửa đối tượng detached thay vì kết quả được quản lý

## 1. Một lỗi khó nhận ra: gọi merge đúng nhưng sửa nhầm object

Một service nhận một entity đã detached, gọi merge, rồi tiếp tục sửa object đầu vào:

~~~java
PurchaseOrder detached = loadFromPreviousRequest();

entityManager.merge(detached);

detached.setStatus("CONFIRMED");
~~~

Lập trình viên có thể nghĩ merge đã gắn lại chính object detached vào persistence context. Nhưng theo semantics của Jakarta Persistence, merge sao chép state của object nguồn sang một managed instance, rồi trả về managed instance đó. Object đầu vào vẫn detached.

Đoạn code trên có thể làm mất thay đổi CONFIRMED: Hibernate theo dõi managed instance được trả về, còn lệnh setStatus lại sửa object detached cũ. Nếu không có một thao tác merge tiếp theo, thay đổi này không được dirty checking ghi xuống database.

Cách đúng:

~~~java
PurchaseOrder managed = entityManager.merge(detached);
managed.setStatus("CONFIRMED");
~~~

Hoặc trong nhiều workflow nghiệp vụ, tải entity đang managed trong transaction, kiểm tra quyền và business rules, rồi thay đổi trực tiếp managed entity.

Lỗi này thường xuất hiện sau khi:

- Entity được serialize thành JSON rồi gửi qua request khác.
- Entity được load trong transaction trước, sau đó dùng ngoài transaction.
- Một service nhận object từ cache, message hoặc tầng khác.
- Developer gọi clear, detach hoặc đóng persistence context.
- Spring Data save trả về một instance khác nhưng code bỏ qua giá trị trả về.
- Một DTO được chuyển thành entity detached rồi merge toàn bộ state.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt new, managed, detached và removed entity states.
2. Giải thích chính xác EntityManager.merge làm gì và trả về object nào.
3. Phân biệt merge với persist, update và reattach.
4. Hiểu vì sao object đầu vào không trở thành managed sau merge.
5. Sử dụng giá trị trả về của merge và Spring Data save.
6. Nhận diện thay đổi bị mất khi sửa nhầm detached object.
7. Hiểu tác động của cascade MERGE lên association graph.
8. Tránh merge toàn bộ entity từ request DTO và ghi đè dữ liệu ngoài ý muốn.
9. Xử lý lazy associations, collections, orphan removal và optimistic locking.
10. Kiểm thử object identity, persistence context và database state.
11. Chọn giữa merge detached state và load-then-update managed state.

Ví dụ sử dụng Java 17+, Jakarta Persistence, Hibernate ORM 6.x và Spring Data JPA. Một số exception/timing phụ thuộc provider và transaction boundary, nhưng quy tắc cốt lõi về merge được định nghĩa bởi Jakarta Persistence.

## 3. Bốn trạng thái của entity

JPA entity có lifecycle. Cùng một object Java có thể chuyển qua các trạng thái khác nhau tùy persistence context.

| Trạng thái | Ý nghĩa | Dirty checking |
|---|---|---|
| New / transient | Object mới, chưa được persistence context quản lý và chưa có row tương ứng | Chưa được theo dõi |
| Managed / persistent | Entity thuộc persistence context hiện tại | Có |
| Detached | Entity từng được quản lý nhưng không còn thuộc persistence context đó | Không |
| Removed | Entity managed được đánh dấu xóa | Provider sẽ xóa khi flush/commit |

### 3.1. New entity

~~~java
PurchaseOrder order = new PurchaseOrder();
order.setOrderNumber("SO-001");
~~~

Object vừa được tạo chưa được EntityManager quản lý.

### 3.2. Managed entity

~~~java
entityManager.persist(order);
~~~

Sau persist, entity trở thành managed. Hoặc:

~~~java
PurchaseOrder order =
    entityManager.find(PurchaseOrder.class, id);
~~~

Nếu tìm thấy, entity trả về thuộc persistence context hiện tại.

### 3.3. Detached entity

~~~java
entityManager.detach(order);
~~~

Entity cũng có thể trở thành detached khi EntityManager/Session đóng, persistence context bị clear hoặc lifecycle scope kết thúc. Object vẫn tồn tại trong heap, nhưng Hibernate không còn theo dõi thay đổi của nó.

### 3.4. Removed entity

~~~java
entityManager.remove(order);
~~~

Entity được đánh dấu removed trong persistence context; SQL DELETE thường được thực hiện khi flush.

### 3.5. Trạng thái là quan hệ giữa object và persistence context

Một object không tự mang cờ managed toàn cục. Entity có thể managed trong EntityManager A nhưng detached đối với EntityManager B. Không chia sẻ managed entity giữa nhiều threads/EntityManagers.

## 4. Persistence context là gì?

Persistence context là vùng làm việc mà JPA/Hibernate quản lý các entity instances. Nó có identity map: trong cùng context, một persistent identity (entity type + primary key) được đại diện bởi một managed instance duy nhất.

~~~text
EntityManager / Persistence Context
  |
  +-- PurchaseOrder#101 -> managed instance A
  +-- Customer#21       -> managed instance B
  +-- OrderItem#501     -> managed instance C
~~~

Khi query lại Order 101 trong cùng context, provider thường trả cùng managed instance A, không tạo một object managed khác cho cùng identity.

### 4.1. Dirty checking

~~~java
PurchaseOrder order =
    entityManager.find(PurchaseOrder.class, 101L);

order.setStatus("CONFIRMED");
~~~

Không cần gọi update để Hibernate biết thay đổi của managed entity. Khi flush, provider phát UPDATE nếu state thay đổi.

### 4.2. Detached object không có dirty checking

~~~java
entityManager.detach(order);
order.setStatus("CONFIRMED");
~~~

Thay đổi trên object detached không được tự động ghi xuống database.

### 4.3. Merge truyền state vào context

Merge không mở lại persistence context cũ. Nó đưa state từ object detached vào một instance được quản lý bởi context hiện tại.

## 5. Semantics chính xác của EntityManager.merge()

~~~java
PurchaseOrder managed = entityManager.merge(detached);
~~~

Về mặt khái niệm:

1. Provider nhận state của object nguồn.
2. Provider tìm hoặc tạo một instance đích managed tương ứng trong persistence context.
3. State của object nguồn được copy vào object đích theo mapping và cascade semantics.
4. Provider trả về object đích managed.
5. Object nguồn vẫn detached nếu ban đầu nó detached.

### 5.1. Hai biến có thể khác object identity

~~~java
PurchaseOrder managed = entityManager.merge(detached);
assertNotSame(detached, managed);
~~~

Đây là hành vi bình thường và thường là điều cần nhớ nhất.

### 5.2. Cùng persistent identity, khác Java object

~~~text
detached object: PurchaseOrder#101, status=DRAFT
       |
       | merge()
       v
managed object:  PurchaseOrder#101, status=DRAFT
~~~

Hai object có thể biểu diễn cùng row ID 101, nhưng chỉ managed object thuộc persistence context hiện tại.

### 5.3. Sửa object nguồn sau merge không sửa target

~~~java
PurchaseOrder managed = entityManager.merge(detached);
detached.setStatus("CONFIRMED");
// managed có thể vẫn là DRAFT.
~~~

Đây chính là lỗi của bài học.

### 5.4. Luôn dùng giá trị trả về

~~~java
PurchaseOrder managed = entityManager.merge(detached);
managed.setStatus("CONFIRMED");
~~~

Nếu method trả entity, hãy trả managed instance hoặc DTO được map từ managed instance theo transaction design.

## 6. Ví dụ lỗi đầy đủ

Entity:

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @Column(nullable = false)
    private String orderNumber;

    @Column(nullable = false)
    private String status;

    protected PurchaseOrder() {}

    public void setStatus(String status) {
        this.status = status;
    }

    public String getStatus() {
        return status;
    }
}
~~~

Service sai:

~~~java
@Transactional
public void confirm(PurchaseOrder detached) {
    entityManager.merge(detached);
    detached.setStatus("CONFIRMED");
}
~~~

Giả sử detached object có ID 101 và status DRAFT:

1. merge(detached) tạo/nhận managed instance trong context.
2. State DRAFT được copy vào managed instance.
3. Method bỏ qua reference trả về.
4. detached.setStatus thay đổi object nguồn.
5. Khi transaction flush, managed instance vẫn có thể là DRAFT.
6. Database giữ DRAFT, dù object detached bên ngoài hiển thị CONFIRMED.

### 6.1. Sửa lỗi tối thiểu

~~~java
@Transactional
public void confirm(PurchaseOrder detached) {
    PurchaseOrder managed = entityManager.merge(detached);
    managed.setStatus("CONFIRMED");
}
~~~

### 6.2. Sửa theo hướng load-then-update

~~~java
@Transactional
public void confirm(Long orderId) {
    PurchaseOrder managed = entityManager.find(
        PurchaseOrder.class, orderId);

    if (managed == null) {
        throw new OrderNotFoundException(orderId);
    }

    managed.setStatus("CONFIRMED");
}
~~~

Phương án này thường dễ kiểm soát hơn cho một command nghiệp vụ: service tải state hiện tại, kiểm tra điều kiện, rồi thay đổi managed entity.

## 7. Merge không phải reattach

Một số API Hibernate cũ có Session.update hoặc khái niệm reattach detached object. JPA merge có semantics khác.

| Thao tác | Ý nghĩa |
|---|---|
| persist(newEntity) | Đưa new entity vào trạng thái managed; dự kiến INSERT |
| merge(detached) | Copy state vào managed instance; trả instance managed |
| find(type,id) | Tải/nhận managed instance theo identity |
| detach(entity) | Loại entity khỏi persistence context |
| clear() | Detach tất cả managed entities |
| remove(managed) | Đánh dấu managed entity để xóa |

### 7.1. Cách diễn đạt chính xác

Nói merge reattach entity dễ khiến người đọc nghĩ object nguồn trở lại managed. Cách diễn đạt chính xác hơn: merge copy state sang managed instance.

### 7.2. Hibernate Session.merge()

Hibernate Session.merge cung cấp behavior tương tự JPA. Không chuyển sang API native chỉ để mong object nguồn được attach; kiểm tra semantics API đúng version.

### 7.3. JPA không có EntityManager.update()

JPA không cung cấp EntityManager.update theo nghĩa Hibernate cũ. Managed entity được dirty-check tự động; detached state cần merge hoặc load managed rồi áp dụng changes.

## 8. Persist và merge khác nhau thế nào?

### 8.1. Persist cho new entity

~~~java
PurchaseOrder order = new PurchaseOrder();
order.setOrderNumber("SO-001");
entityManager.persist(order);
~~~

Object đầu vào trở thành managed trong context.

### 8.2. Merge cho detached/existing state

~~~java
PurchaseOrder managed = entityManager.merge(detached);
~~~

Object trả về managed; object nguồn không được gắn lại.

### 8.3. Persist detached entity

~~~java
entityManager.persist(detached);
~~~

Đây không phải cách để gắn lại detached entity. Provider có thể ném EntityExistsException hoặc PersistenceException khi phát hiện persistent identity đã tồn tại; thời điểm phát hiện phụ thuộc provider.

### 8.4. Merge new entity

JPA merge cũng có thể nhận new/transient entity: provider tạo managed instance mới và copy state; INSERT sẽ được thực hiện theo lifecycle. Persist thường là lựa chọn rõ ràng hơn khi tạo mới.

### 8.5. Bảng so sánh

| Câu hỏi | persist | merge |
|---|---|---|
| Đầu vào thường gặp | New entity | Detached hoặc new state |
| Object đầu vào managed? | Có | Nếu detached thì vẫn detached |
| Giá trị trả về | void | Managed instance |
| Cần giữ returned object? | Không có return | Có, nếu cần thao tác tiếp |
| State copy sang instance khác? | Không theo semantics merge | Có |
| Mục tiêu | Bắt đầu lifecycle persistence | Đồng bộ state vào context |

## 9. Vì sao merge có thể trả về object khác?

Một persistence context không thể quản lý hai object instances khác nhau cho cùng một persistent identity.

~~~java
PurchaseOrder managedExisting =
    entityManager.find(PurchaseOrder.class, 101L);

PurchaseOrder detached = detachedCopyWithId(101L);
detached.setStatus("CONFIRMED");

PurchaseOrder result = entityManager.merge(detached);
~~~

Provider copy state vào managedExisting và trả managed instance tương ứng. Thông thường:

~~~java
assertSame(managedExisting, result);
assertNotSame(detached, result);
~~~

### 9.1. Tránh hai bản managed cùng ID

Nếu provider attach luôn object detached trong khi context đã có một instance cùng ID, identity map sẽ bị vi phạm. Merge giúp hợp nhất state vào instance managed hiện có.

### 9.2. Merge không phải object copy nông đơn giản

Provider xử lý mapped attributes, relationships, cascades, versions và entity identity. Không giả định chỉ một BeanUtils.copyProperties được gọi.

### 9.3. Merge có thể phát SQL

Merge detached entity có thể yêu cầu provider đọc entity đích để copy/so sánh state. SQL timing phụ thuộc provider, identity availability, mappings và context. Không giả định merge luôn chỉ là thao tác memory.

## 10. Spring Data JPA save() cũng cần giữ giá trị trả về

Repository:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
~~~

Spring Data JPA save(entity) thường chọn:

- EntityManager.persist(entity) nếu entity được xác định là new.
- EntityManager.merge(entity) nếu entity được xác định là existing.

Do đó:

~~~java
PurchaseOrder saved = repository.save(entity);
~~~

là pattern an toàn khi caller cần instance managed/returned.

### 10.1. Lỗi bỏ qua return value

~~~java
repository.save(detached);
detached.setStatus("CONFIRMED");
~~~

Nếu Spring Data chọn merge, detached vẫn detached. Thay đổi tiếp theo không được dirty checking.

### 10.2. Cách đúng

~~~java
PurchaseOrder managed = repository.save(detached);
managed.setStatus("CONFIRMED");
~~~

### 10.3. save() không phải lúc nào cũng merge

Nếu entity new và Spring Data chọn persist, chính object đầu vào được managed. Vì vậy lỗi có thể xuất hiện ở entity có ID/version/new-detection khác nhau, khiến test một case pass nhưng case detached lại fail.

### 10.4. Không gọi save() sau mọi setter trên managed entity

Trong transaction, entity được load từ repository đã managed. Dirty checking đủ để ghi thay đổi khi flush:

~~~java
@Transactional
public void confirm(Long id) {
    PurchaseOrder order = repository.findById(id)
        .orElseThrow();
    order.setStatus("CONFIRMED");
}
~~~

Gọi save lại có thể không cần thiết. Điều quan trọng là transaction và persistence context vẫn mở.

### 10.5. saveAndFlush()

saveAndFlush ép flush sau save theo Spring Data implementation. Nó không biến detached input thành managed nếu đường đi dùng merge; hãy vẫn dùng giá trị trả về.

## 11. Spring Data entity new detection có thể làm hành vi khác nhau

Spring Data JPA phải quyết định entity new hay existing.

### 11.1. ID null

Với generated ID thông thường, ID null thường được coi là new.

### 11.2. ID non-null

Với assigned ID/UUID, ID đã có thể khiến entity được coi là existing, tùy version property và entity metadata.

### 11.3. @Version

Một nullable non-primitive version property có thể được dùng trong new detection. Nếu version null, entity có thể được nhận diện là new ngay cả khi ID đã được gán.

### 11.4. Persistable.isNew()

Spring Data cho phép entity implement Persistable<ID> để điều khiển new detection. Cần quản lý flag new/persisted đúng lifecycle.

### 11.5. Vì sao điều này liên quan merge bug?

Cùng một dòng:

~~~java
repository.save(entity);
entity.setStatus("CONFIRMED");
~~~

có thể hoạt động khi save gọi persist nhưng thất bại khi save gọi merge. Giữ return value giúp code không phụ thuộc vào việc đầu vào tình cờ được persist hay merge.

## 12. Merge và cascade MERGE

Association có thể khai báo:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.MERGE
)
private List<OrderItem> items;
~~~

Khi merge Order, state của associated entities có cascade MERGE có thể được merge đệ quy.

### 12.1. Cascade MERGE không attach source child

Mỗi detached child có thể được copy sang managed child instance tương ứng. Nếu tiếp tục sửa list/child objects trong detached graph sau merge, các thay đổi đó không tự đi vào managed graph.

### 12.2. Giữ managed graph

~~~java
PurchaseOrder managed = entityManager.merge(detached);

for (OrderItem item : managed.getItems()) {
    item.setQuantity(item.getQuantity() + 1);
}
~~~

Thao tác trên managed association/children trong context.

### 12.3. Cascade MERGE không phải Cascade PERSIST

CascadeType.MERGE và CascadeType.PERSIST có semantics khác. Nếu một new child được gắn vào detached parent, cần hiểu cascade operation nào được áp dụng và provider xử lý state thế nào.

### 12.4. Cascade ALL rộng có thể merge graph ngoài dự kiến

CascadeType.ALL bao gồm MERGE, PERSIST, REMOVE, REFRESH và DETACH. Dùng ALL trên association chỉ khi lifecycle ownership thật sự yêu cầu. Không thêm cascade MERGE mọi nơi để sửa lỗi detached.

## 13. Merge graph có thể tải nhiều dữ liệu và gây N+1

Detached graph có thể gồm:

~~~text
Order
  -> Customer
  -> Items[]
      -> Product
  -> Shipments[]
      -> Warehouse
~~~

Merge một detached graph lớn có thể yêu cầu provider đọc state hiện tại của các entities đích, kiểm tra identity và copy associations.

### 13.1. Chi phí

- Nhiều SELECT để tìm/load managed targets.
- Dirty checking trên graph lớn.
- Cascade traversal sâu.
- Conflict giữa detached graph và state hiện tại.
- Tăng memory trong persistence context.

### 13.2. Không merge graph chỉ để sửa một field

Nếu command chỉ đổi status, tải managed Order và gọi domain method sẽ rõ hơn và thường ít SQL hơn.

### 13.3. Merge graph có thể chứa association chưa load

Detached object có thể mang collection rỗng vì serializer không include association, chứ không phải collection thật sự rỗng trong database. Merge graph có thể copy trạng thái đó vào managed entity theo mapping/cascade semantics và gây ghi đè hoặc orphan changes ngoài ý muốn.

### 13.4. Không coi detached graph là PATCH document

Một entity graph serialized không có metadata đủ để phân biệt:

- Field không gửi.
- Field gửi null.
- Collection không load.
- Collection chủ ý xóa hết.

Dùng command/DTO có semantics rõ thay cho merge một entity graph từ HTTP request.

## 14. Detached entity và lazy associations

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
~~~

Sau khi EntityManager đóng, proxy có thể chưa được initialize. Truy cập:

~~~java
detached.getCustomer().getName();
~~~

có thể ném LazyInitializationException trong Hibernate nếu proxy cần Session nhưng không còn Session.

### 14.1. Merge không tự biến mọi proxy nguồn thành loaded graph

Merge có semantics riêng cho loaded/unloaded state theo JPA/provider. Không dựa vào detached object để duyệt mọi association sau merge; dùng managed return value và fetch plan phù hợp.

### 14.2. Truy cập association trên managed result

~~~java
PurchaseOrder managed = entityManager.merge(detached);
String customerName = managed.getCustomer().getName();
~~~

Vẫn cần transaction/session mở và fetch behavior phù hợp.

### 14.3. Không merge chỉ để hết LazyInitializationException

Nếu use case chỉ đọc dữ liệu, hãy query DTO/entity graph trong transaction phù hợp. Merge là thao tác đồng bộ state, có thể gây writes và side effects không cần thiết.

### 14.4. OSIV không làm detached semantics biến mất

Open Session in View có thể giữ Session mở trong request web, nhưng không biến object từ request trước thành managed trong request hiện tại. Persistence context và transaction boundary vẫn cần được hiểu rõ.

## 15. Merge detached entity có thể ghi đè dữ liệu mới hơn

Giả sử:

1. T1 load Order 101, status DRAFT, note A.
2. Entity trở thành detached.
3. T2 đổi note thành B và commit.
4. T1 merge object cũ có note A.

Nếu không có optimistic version conflict/field-level policy phù hợp, merge có thể copy state cũ lên managed target và ghi đè giá trị mới hơn.

### 15.1. Merge không phải patch

Merge đồng bộ state của entity detached theo persistence semantics; nó không tự hiểu chỉ field nào người dùng vừa thay đổi.

### 15.2. @Version

~~~java
@Version
private long version;
~~~

Version giúp phát hiện stale updates khi provider dùng version semantics cho entity. Detached instance có version cũ có thể bị từ chối với optimistic locking exception, thay vì âm thầm ghi đè, tùy provider/lifecycle.

### 15.3. Version không giải quyết mọi partial update

Version phát hiện conflict ở entity level. Nó không tự giải quyết field nào trong DTO được phép thay đổi, collection nào chưa load, quy tắc merge từng field, cross-entity invariants hoặc external side effects.

### 15.4. Test version mapping

Concurrency test cần xác nhận version column được mapping đúng, UPDATE có version predicate và stale write bị phát hiện.

## 16. DTO update và nguy cơ null overwrite

Một API nhận:

~~~json
{
  "id": 101,
  "status": "CONFIRMED"
}
~~~

Developer tạo entity mới:

~~~java
PurchaseOrder detached = new PurchaseOrder();
detached.setId(request.id());
detached.setStatus(request.status());
repository.save(detached);
~~~

Nếu save gọi merge, các field không có trong request nhưng đang null trên object detached có thể được copy sang managed entity, gây mất orderNumber, totalAmount hoặc customer reference tùy mapping/provider semantics.

### 16.1. Entity không phải DTO

Không nhận entity đầy đủ từ client làm update contract. DTO nên biểu diễn chính xác field được phép cập nhật và semantics null/omitted.

### 16.2. Load rồi apply command

~~~java
@Transactional
public void updateStatus(
        Long orderId,
        UpdateOrderStatusCommand command) {

    PurchaseOrder managed = repository.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);

    managed.changeStatus(command.status());
}
~~~

Những field không thuộc command giữ nguyên vì không bị copy từ một object thiếu dữ liệu.

### 16.3. PATCH cần phân biệt omitted và null

Nếu null có nghĩa xóa giá trị, còn omitted có nghĩa không thay đổi, DTO cần biểu diễn hai trạng thái đó rõ ràng. Java field null đơn thuần không đủ phân biệt.

### 16.4. Collection replacement phải có semantics riêng

Một request items=[] có thể có nghĩa xóa toàn bộ items; request không có items có thể có nghĩa giữ nguyên. Không merge một entity detached có collection rỗng vì serializer bỏ qua association.

## 17. Merge với collection và orphanRemoval

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderItem> items = new ArrayList<>();
~~~

### 17.1. Detached collection không load không đồng nghĩa empty collection

Nếu DTO/serializer tạo entity với items là ArrayList rỗng, object nguồn có vẻ có collection rỗng. Khi merge, provider có thể xử lý collection state/cascade và orphan removal theo persistence semantics. Điều này có thể dẫn tới DELETE children ngoài ý muốn nếu state được coi là authoritative.

### 17.2. Không thay collection managed bằng collection detached tùy tiện

Trong managed aggregate, thao tác collection qua domain methods:

~~~java
managed.removeItem(itemId);
managed.addItem(newItem);
~~~

thường rõ ràng hơn gán collection từ detached object.

### 17.3. Orphan removal cần được test với database state

Sau flush, SQL độc lập kiểm tra child rows còn hay đã bị xóa. Đừng chỉ assert collection size trong memory, vì collection state có thể không phản ánh đầy đủ SQL/foreign key outcomes.

### 17.4. Cascade REMOVE và merge graph

Merge không đồng nghĩa xóa mọi child bị thiếu trong source ở mọi mapping. Behavior phụ thuộc collection loaded state, cascade, orphanRemoval và provider semantics. Viết test theo use case thực.

## 18. Merge và entity có cùng ID đã tồn tại trong context

~~~java
PurchaseOrder managed = entityManager.find(
    PurchaseOrder.class, 101L);

PurchaseOrder detached = detachedCopyWithId(101L);
detached.setStatus("CONFIRMED");

PurchaseOrder result = entityManager.merge(detached);
~~~

Trong trường hợp này, provider có thể copy state vào instance managed đã có:

~~~java
assertSame(managed, result);
assertNotSame(detached, result);
~~~

### 18.1. Managed instance cũ có thể bị overwrite

Nếu managed trước merge có thay đổi chưa flush, state từ detached source có thể xung đột hoặc ghi đè tùy merge order/attribute state. Không trộn hai nguồn thay đổi cùng lúc mà không có policy.

### 18.2. Tránh merge khi context đã có managed entity

Nếu entity đã được load trong transaction, sửa trực tiếp managed instance. Không tạo detached copy rồi merge lại chỉ để cập nhật một field.

### 18.3. Không giữ hai object cùng ID như hai nguồn state độc lập

Sau merge, chỉ dùng managed result cho mọi thao tác tiếp theo. Object detached có thể vẫn được caller giữ, nhưng không nên tiếp tục coi nó là nguồn state hiện hành.

## 19. Merge và optimistic locking

~~~java
@Version
private long version;
~~~

Một detached instance có version 4 trong khi database đã lên version 5 có thể gây optimistic lock conflict khi merge/flush. JPA quy định optimistic locking checks áp dụng cho versioned entities; exception có thể xuất hiện trong merge, flush hoặc commit tùy timing/provider.

### 19.1. Không bỏ qua OptimisticLockException

Nếu stale write bị phát hiện:

- Rollback transaction.
- Reload state mới.
- Báo conflict hoặc áp dụng merge policy có chủ đích.
- Không retry mù với detached object cũ.

### 19.2. Retry phải dựa trên command

Nếu retry một command ConfirmOrder, tải Order mới rồi kiểm tra status/version/business rule. Đừng merge lại detached graph cũ vì nó có thể ghi đè state vừa thay đổi.

### 19.3. Entity không có @Version

Nếu không có optimistic versioning, concurrent detached merges có thể ghi đè state mới hơn mà không phát hiện. Cân nhắc @Version cho entities có concurrent updates.

### 19.4. Version field trong DTO

Nếu API cho client cập nhật dựa trên version, truyền version token/ETag và kiểm tra nó ở service. Không để client tự sửa version field entity tùy ý.

## 20. Merge và security: không tin detached graph từ client

Một client gửi:

~~~json
{
  "id": 101,
  "organizationId": 8,
  "customer": {"id": 82},
  "status": "CONFIRMED",
  "totalAmount": 0.01
}
~~~

Nếu server deserialize trực tiếp thành entity rồi merge, client có thể cố thay đổi organization ownership, Customer reference, total amount, audit fields, approval state hoặc version.

### 20.1. Merge không phải authorization

JPA merge không kiểm tra caller có quyền trên entity hoặc association. Service phải xác minh principal, organization scope và permissions trước khi thay đổi managed state.

### 20.2. Load scoped entity

~~~java
PurchaseOrder managed = repository
    .findByIdAndOrganizationId(orderId, trustedOrgId)
    .orElseThrow(OrderNotFoundException::new);
~~~

### 20.3. Whitelist field updates

Chỉ áp dụng field nằm trong command:

~~~java
managed.changeStatus(command.status());
~~~

Không copy tất cả request properties vào entity.

### 20.4. Association phải được tải trong scope

Nếu command thay Customer, tải Customer bằng ID + trustedOrgId, xác minh quyền và domain invariants; không gán một stub entity từ client.

## 21. Load-then-update thường phù hợp với command nghiệp vụ

~~~java
@Transactional
public void approve(Long orderId, UserPrincipal principal) {
    Long organizationId =
        authorization.requireActiveOrganization(principal);

    PurchaseOrder order = repository
        .findByIdAndOrganizationId(orderId, organizationId)
        .orElseThrow(OrderNotFoundException::new);

    authorization.requirePermission(
        principal, organizationId, "ORDER_APPROVE");

    order.approve();
}
~~~

### 21.1. Lợi ích

- Làm việc với managed entity.
- Đọc state hiện tại trong transaction/isolation.
- Domain methods giữ invariants.
- Chỉ cập nhật field được phép.
- Dễ kết hợp @Version và authorization.
- Không cần merge detached graph.

### 21.2. Dirty checking ghi thay đổi

Khi transaction flush/commit, Hibernate phát UPDATE nếu state thay đổi. Không cần gọi repository.save(order) lần nữa trong cùng transaction.

### 21.3. Query scoped tránh IDOR

Tìm entity theo cả ID và organization scope, sau khi xác minh membership. ID đơn lẻ không chứng minh quyền truy cập.

### 21.4. Khi nào merge vẫn hợp lý?

Merge có thể phù hợp khi detached graph được tạo trong workflow persistence có chủ đích; state source là authoritative và đầy đủ; cascade graph được kiểm soát; optimistic locking/version được xử lý; caller dùng managed result.

## 22. Tạo command DTO thay vì gửi entity detached

~~~java
public record ConfirmOrderCommand(
    String confirmationReference,
    long expectedVersion
) {}
~~~

Service:

~~~java
@Transactional
public void confirm(
        Long orderId,
        Long organizationId,
        ConfirmOrderCommand command) {

    PurchaseOrder order = repository
        .findByIdAndOrganizationId(orderId, organizationId)
        .orElseThrow(OrderNotFoundException::new);

    if (order.getVersion() != command.expectedVersion()) {
        throw new ConcurrentOrderModificationException();
    }

    order.confirm(command.confirmationReference());
}
~~~

Ví dụ cần expose version getter và định nghĩa domain exceptions tương ứng. Ý chính: command biểu diễn hành động, không mang toàn bộ entity state để merge.

### 22.1. Command có thể bất biến

Java record giúp command payload rõ và không bị thay đổi trong quá trình xử lý.

### 22.2. Validation ở service/domain

Kiểm tra status hiện tại, permission, Customer state, amount và transition rules trên managed state. Không dựa vào state client gửi.

### 22.3. Response DTO

Sau update, map kết quả từ managed entity sang response DTO trước khi persistence context đóng. Không trả detached graph rộng không cần thiết.

## 23. Detached state từ REST serialization

Một lỗi phổ biến:

~~~java
@PutMapping("/orders/{id}")
public PurchaseOrder update(
        @PathVariable Long id,
        @RequestBody PurchaseOrder order) {
    order.setId(id);
    return repository.save(order);
}
~~~

### 23.1. Vì sao nguy hiểm?

- Request body trở thành entity detached/new-shaped.
- Client có thể gửi field không được phép.
- Null fields có thể ghi đè database values.
- Collections có thể thiếu hoặc rỗng.
- Associations có thể trỏ sai tenant.
- Version conflict không được xử lý rõ.
- Lazy proxies/serialization cycles có thể gây lỗi.

### 23.2. Tách request DTO

~~~java
public record UpdateOrderRequest(
    String deliveryNote,
    String requestedDeliveryDate
) {}
~~~

### 23.3. Load và apply

~~~java
@Transactional
public OrderResponse update(
        Long id,
        Long organizationId,
        UpdateOrderRequest request) {

    PurchaseOrder order = repository
        .findByIdAndOrganizationId(id, organizationId)
        .orElseThrow(OrderNotFoundException::new);

    order.updateDeliveryDetails(
        request.deliveryNote(),
        parseDate(request.requestedDeliveryDate())
    );

    return mapper.toResponse(order);
}
~~~

### 23.4. PUT và PATCH

PUT thường biểu diễn replacement theo resource contract; PATCH biểu diễn partial modification. Entity merge không tự cung cấp semantics HTTP đó. Hãy định nghĩa field presence/null behavior rõ.

## 24. Detached graph từ cache hoặc message queue

Entity có thể được serialize vào Redis/application cache, Kafka/RabbitMQ message, distributed session hoặc batch file. Sau khi deserialize, đó là object Java mới, không thuộc persistence context trước.

### 24.1. Không coi serialized entity là managed snapshot

Nó có thể cũ, thiếu association, thiếu lazy state hoặc thuộc schema version khác.

### 24.2. Message nên mang command/identifier

~~~json
{
  "eventType": "ConfirmOrderRequested",
  "orderId": 101,
  "organizationId": 7,
  "requestedBy": 42,
  "expectedVersion": 4
}
~~~

Consumer tải entity managed theo ID/scope, xác minh contract rồi áp dụng command.

### 24.3. Idempotency

Message có thể được xử lý lại. Tải managed state mới và kiểm tra trạng thái/idempotency key trước khi thực hiện; không merge nguyên entity snapshot cũ từ message.

### 24.4. Schema evolution

Serialized entity gắn với Java class structure và mapping version. Command/event DTO có versioned contract dễ kiểm soát hơn entity graph.

## 25. Merge và @DynamicUpdate

Hibernate @DynamicUpdate có thể sinh UPDATE chỉ gồm các columns thay đổi theo dirty state. Nhưng nó không làm merge thành partial patch.

### 25.1. Merge vẫn copy source state

Nếu detached source có field null, field đó vẫn có thể trở thành state managed; dynamic update có thể phát UPDATE column đó vì nó đã thay đổi.

### 25.2. Dynamic update không biết field omitted

JPA entity không tự biết JSON field bị omitted. Một null trong entity là state null, không phải “không thay đổi”.

### 25.3. Partial updates nên được biểu diễn bằng command

Chỉ set các field được yêu cầu. Nếu cần update một số cột trực tiếp, có thể dùng explicit JPQL/native update với predicates và version checks rõ ràng.

### 25.4. Test SQL columns

Nếu performance/trigger logic phụ thuộc columns được update, capture SQL hoặc đối soát row/audit. Đừng dùng @DynamicUpdate để che lỗi merge detached state.

## 26. Merge và database-generated values

Database có thể set default timestamps, trigger-maintained audit fields, generated columns hoặc version values theo strategy.

Sau merge, managed result có thể chưa tự phản ánh mọi generated values cho tới flush/refresh hoặc generated-value mapping.

### 26.1. Flush

~~~java
PurchaseOrder managed = entityManager.merge(detached);
entityManager.flush();
~~~

### 26.2. Refresh khi cần

~~~java
entityManager.refresh(managed);
~~~

Refresh reload state theo mapping từ database. Không gọi refresh trước khi flush nếu muốn giữ pending changes chưa được ghi; refresh có thể ghi đè in-memory state bằng DB state.

### 26.3. SQL độc lập để xác minh

~~~sql
SELECT created_at, updated_at, version
FROM purchase_orders
WHERE id = :id;
~~~

JDBC query xác nhận raw row. Đây là cách tách lỗi database ghi đúng nhưng managed object chưa refresh khỏi lỗi database ghi sai.

## 27. Merge và transaction boundaries

~~~java
@Transactional
public void mergeAndUpdate(PurchaseOrder detached) {
    PurchaseOrder managed = entityManager.merge(detached);
    managed.setStatus("CONFIRMED");
}
~~~

### 27.1. Transaction kết thúc

Sau khi transaction kết thúc và persistence context đóng/detach theo lifecycle, managed object trả về có thể trở thành detached. Không giữ reference đó rồi sửa ở một thời điểm khác và mong dirty checking vẫn hoạt động.

### 27.2. Method không có transaction

Một số repository methods có transaction riêng, nhưng sau khi method kết thúc, entity trả về có thể không còn managed trong context của caller. Nếu cần thao tác tiếp, đặt service transaction boundary rõ hoặc gọi service method quản lý toàn bộ workflow.

### 27.3. @Transactional self-invocation

Spring proxy-based transaction management có thể không áp dụng annotation khi method gọi nội bộ qua this. Nếu transaction không mở như kỳ vọng, EntityManager lifecycle và merge behavior có thể khác. Kiểm tra transaction boundary thực tế.

### 27.4. Async threads

Transaction/persistence context không tự truyền sang thread khác. Không sửa managed entity từ thread ngoài transaction. Worker nên nhận ID/command rồi tải entity trong transaction riêng.

## 28. Merge và cascade trên nhiều aggregate roots

Giả sử Order và Customer là hai aggregate roots độc lập. Order có Customer reference:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
~~~

Thêm CascadeType.MERGE từ Order sang Customer có thể làm merge state Customer khi merge Order.

### 28.1. Cẩn thận với shared references

Customer có thể được nhiều Orders cùng tham chiếu. Một detached Customer snapshot cũ trong Order graph có thể ghi đè state của Customer mà use case khác vừa cập nhật.

### 28.2. Cascade theo ownership

Cascade MERGE thường phù hợp khi child lifecycle phụ thuộc parent hoặc aggregate thực sự sở hữu child. Với shared entities như Customer, Product, User, Role, không tự động cascade merge mọi nơi.

### 28.3. Tải shared entity managed riêng

Nếu command thay Customer, tải Customer theo ID/scope trong transaction, rồi gán association managed. Không merge Customer snapshot nhúng trong Order request.

### 28.4. Aggregate boundary

Nếu merge phải đi qua hàng chục shared entities, đó có thể là dấu hiệu persistence boundary chưa rõ.

## 29. Entity equality không làm object detached trở thành managed

~~~java
PurchaseOrder a = detachedOrderWithId(101L);
PurchaseOrder b = entityManager.find(
    PurchaseOrder.class, 101L);
~~~

Hai object có thể equals true nếu entity equality dựa trên ID. Nhưng điều đó không có nghĩa object a được quản lý.

### 29.1. == và equals khác nhau

== kiểm tra object identity; equals kiểm tra equality theo implementation. Hibernate persistence context quản lý instance cụ thể.

### 29.2. Set/Map có thể gây nhầm

Nếu detached và managed object cùng ID và equals/hashCode coi bằng nhau, thêm cả hai vào Set có thể chỉ giữ một. Điều đó không tự chọn object managed. Sau merge, hãy giữ returned instance.

### 29.3. Không dùng equals để xác minh managed

~~~java
assertTrue(entityManager.contains(managed));
assertFalse(entityManager.contains(detached));
~~~

## 30. entityManager.contains() giúp chẩn đoán

~~~java
assertFalse(entityManager.contains(detached));

PurchaseOrder managed = entityManager.merge(detached);

assertTrue(entityManager.contains(managed));
assertFalse(entityManager.contains(detached));
~~~

### 30.1. contains không phải database existence check

contains trả lời entity có thuộc persistence context hiện tại không. Nó không xác nhận row còn tồn tại hoặc transaction đã commit.

### 30.2. Detached entity có thể có ID hợp lệ

ID non-null không có nghĩa managed.

### 30.3. New entity cũng có thể chưa managed

Object mới chưa persist/merge cũng trả false.

### 30.4. Dùng contains trong test lifecycle

Nó hữu ích để chứng minh lỗi bỏ qua merge result, nhưng vẫn nên kiểm tra database row sau flush/commit nếu test nhằm xác minh persistence.

## 31. Test tái hiện lỗi bỏ qua merge result

~~~java
@Test
void changingDetachedInputAfterMergeDoesNotChangeManagedCopy() {
    PurchaseOrder detached = detachedOrderWithId(existingOrderId);
    detached.setStatus("DRAFT");

    entityManager.detach(detached);
    assertFalse(entityManager.contains(detached));

    PurchaseOrder managed = entityManager.merge(detached);

    assertNotSame(detached, managed);
    assertTrue(entityManager.contains(managed));
    assertFalse(entityManager.contains(detached));

    detached.setStatus("CONFIRMED");

    assertEquals("CONFIRMED", detached.getStatus());
    assertEquals("DRAFT", managed.getStatus());
}
~~~

Fixture/constructor cần tạo entity state hợp lệ; ví dụ tập trung vào lifecycle, không phải cách tạo entity production.

### 31.1. Test sửa managed result

~~~java
managed.setStatus("CONFIRMED");
entityManager.flush();
~~~

Sau đó JDBC query kiểm tra:

~~~sql
SELECT status
FROM purchase_orders
WHERE id = :id;
~~~

Kỳ vọng CONFIRMED.

### 31.2. Test bỏ qua return

1. Merge detached DRAFT.
2. Bỏ qua result.
3. Sửa detached thành CONFIRMED.
4. Flush.
5. JDBC query status.
6. Xác nhận database vẫn DRAFT theo state managed đã merge.

### 31.3. Đừng để test transaction rollback che kết quả

Nếu dùng @Transactional trên test, JDBC query cùng transaction sau flush thấy uncommitted update. Điều đó phù hợp để xác nhận flush; nếu muốn kiểm tra commit visibility, mở transaction đọc mới sau khi transaction ghi kết thúc.

## 32. Test Spring Data save() return value

Một repository test nên kiểm tra cả đường persist và merge.

### 32.1. New entity

~~~java
PurchaseOrder newOrder = new PurchaseOrder();
PurchaseOrder saved = repository.save(newOrder);
~~~

Nếu đường đi persist, input thường là managed trong transaction. Kiểm tra:

~~~java
assertTrue(entityManager.contains(saved));
~~~

### 32.2. Detached entity

1. Load Order.
2. Detach/clear context.
3. Sửa detached state.
4. Gọi save và giữ result.
5. Kiểm tra returned instance managed.
6. Sửa returned instance.
7. Flush và JDBC verify.

### 32.3. Test bỏ qua return value

Viết regression test cho code cũ để chứng minh thay đổi sau save trên detached input không được persist.

### 32.4. New detection

Nếu entity dùng UUID assigned hoặc custom Persistable, test cả isNew() để biết save gọi persist hay merge. Không giả định ID non-null luôn đồng nghĩa merge trong mọi entity configuration.

## 33. SQL độc lập xác minh kết quả sau merge

Sau:

~~~java
PurchaseOrder managed = entityManager.merge(detached);
managed.setStatus("CONFIRMED");
entityManager.flush();
~~~

JDBC:

~~~java
String storedStatus = jdbcTemplate.queryForObject(
    "select status from purchase_orders where id = ?",
    String.class,
    managed.getId()
);
assertEquals("CONFIRMED", storedStatus);
~~~

### 33.1. Vì sao không query bằng repository lần nữa?

Repository query có thể trả cùng managed instance trong persistence context. JDBC SELECT đi thẳng database và không dùng L1 entity instance.

### 33.2. Cùng transaction

JDBC query dùng cùng transaction có thể thấy changes sau flush. Nó không chứng minh commit đã xảy ra.

### 33.3. Sau commit

Dùng transaction mới để xác nhận row tồn tại sau commit. Đây là cách kiểm tra trạng thái mà một transaction khác có thể nhìn thấy theo isolation.

### 33.4. Trigger/default

Nếu DB trigger thay đổi status, entity managed có thể chưa refresh. Đọc raw row rồi gọi refresh nếu cần đồng bộ object state.

## 34. Merge và bulk/native updates

~~~java
PurchaseOrder managed = entityManager.find(
    PurchaseOrder.class, id);

jdbcTemplate.update(
    "update purchase_orders set status = ? where id = ?",
    "CANCELLED", id
);
~~~

Managed entity có thể vẫn giữ status cũ. JDBC/native SQL không tự cập nhật persistence context.

### 34.1. Không merge một detached object cũ sau native update

Nếu merge snapshot cũ, state cũ có thể ghi đè native update.

### 34.2. Clear hoặc refresh

Sau khi đảm bảo pending ORM changes đã flush:

~~~java
entityManager.clear();
~~~

hoặc:

~~~java
entityManager.refresh(managed);
~~~

### 34.3. Query sau bulk DML

JPQL bulk DML cũng có thể làm stale managed entities. Dùng clear/refresh theo đúng lifecycle.

### 34.4. Tránh hai nguồn ghi không có policy

Nếu một transaction thay đổi entity qua ORM, transaction khác dùng native SQL và một detached graph được merge sau đó, phải xác định optimistic locking/transaction order. Không dựa vào thứ tự gọi Java để suy ra database state cuối.

## 35. Merge và second-level/application cache

Detached entity có thể đến từ cache:

~~~java
PurchaseOrder cached = cache.get(orderId);
PurchaseOrder managed = entityManager.merge(cached);
~~~

### 35.1. Cache snapshot có thể stale

Merge có thể copy stale values lên managed state. @Version giúp phát hiện một số conflicts, nhưng cache invalidation và command semantics vẫn cần thiết.

### 35.2. Không cache managed entity

Managed entity gắn với persistence context/lazy proxies và không nên được chia sẻ như một object toàn cục. Cache DTO/immutable snapshot hoặc identifiers phù hợp hơn.

### 35.3. Cache key không thay authorization

Nếu entity thuộc organization, cache lookup phải có scope và authorization trước khi trả dữ liệu.

### 35.4. Merge không phải cache refresh

Merge đồng bộ object state vào persistence context; nó không tự làm mới một cache phân tán hoặc giải quyết mọi invalidation.

## 36. Chẩn đoán lỗi trong production

Khi người dùng báo đã sửa object nhưng database không đổi, kiểm tra:

1. Object ban đầu được load trong transaction nào?
2. EntityManager/Session có bị đóng/clear/detach không?
3. Có gọi merge/save không?
4. Return value của merge/save có bị bỏ qua không?
5. Sau merge, code sửa biến nào: source hay returned managed object?
6. Transaction có commit không?
7. Có exception/rollback-only bị che không?
8. Có bulk/native SQL ghi cùng row không?
9. Có @Version conflict không?
10. Có cache hoặc serialization tạo detached copy không?

### 36.1. Log lifecycle có kiểm soát

~~~java
log.debug("input managed={}",
    entityManager.contains(input));

PurchaseOrder managed = entityManager.merge(input);

log.debug("same instance={}", input == managed);
log.debug("input managed after merge={}",
    entityManager.contains(input));
log.debug("result managed={}",
    entityManager.contains(managed));
~~~

Không log toàn bộ entity graph chứa PII/secrets.

### 36.2. SQL logs

Bật Hibernate SQL logging trong test hoặc môi trường diagnostic để xem INSERT/UPDATE thực sự xảy ra lúc nào. Bind parameter logs có thể chứa dữ liệu nhạy cảm; kiểm soát mức log.

### 36.3. Database row là nguồn xác minh

Dùng SQL độc lập để đọc status/version/updated_at sau flush/commit. Không kết luận từ object detached còn nằm trong memory.

## 37. Những anti-pattern cần tránh

### 37.1. Bỏ qua merge result

~~~java
entityManager.merge(detached);
detached.setName("New name");
~~~

### 37.2. Bỏ qua save result

~~~java
repository.save(detached);
return detached;
~~~

### 37.3. Merge entity deserialize từ HTTP

~~~java
repository.save(requestMappedEntity);
~~~

### 37.4. Merge graph lớn để sửa một field

~~~java
entityManager.merge(orderWithEntireGraph);
~~~

### 37.5. Merge stale snapshot sau khi native SQL cập nhật

~~~java
entityManager.merge(cachedOldOrder);
~~~

### 37.6. Tiếp tục dùng source object như managed

~~~java
PurchaseOrder managed = entityManager.merge(detached);
detached.getItems().get(0).setQuantity(5);
~~~

### 37.7. Dùng merge để né transaction design

Merge không thay thế việc xác định transaction boundary, persistence context scope và command lifecycle.

## 38. Quy tắc chọn merge hay load-then-update

| Tình huống | Hướng thường phù hợp |
|---|---|
| Tạo entity mới trong transaction | persist hoặc repository.save |
| Entity đã managed trong transaction | Sửa trực tiếp; dirty checking |
| Entity detached, state đầy đủ và authoritative | merge; giữ managed return value |
| HTTP PATCH chỉ đổi vài field | Load managed + apply command |
| Entity lấy từ cache/message | Gửi ID/command; load managed state mới |
| Cần thay đổi aggregate với children | Load aggregate, reconcile qua domain methods |
| Stale detached state có @Version | Xử lý optimistic conflict; không retry mù |
| Chỉ cần đọc dữ liệu detached | DTO/projection; không merge |
| Cần native SQL/bulk update | Update có predicate/version; clear/refresh context |

### 38.1. Một câu hỏi quyết định

Object này có phải state đầy đủ, đáng tin cậy và có quyền trở thành nguồn state của entity hiện tại không?

Nếu câu trả lời không rõ, đừng merge toàn bộ graph. Hãy tải managed entity và áp dụng command có field whitelist.

### 38.2. Merge phù hợp khi nào?

Khi detached state thực sự là input cần đồng bộ, cascade graph được thiết kế, version/conflict policy rõ, và caller hiểu rằng phải dùng returned instance.

### 38.3. Load-then-update phù hợp khi nào?

Khi một request muốn thay đổi một phần entity, cần authorization/domain checks hoặc database hiện tại là source of truth.

## 39. Ví dụ service hoàn chỉnh dùng managed entity

Command:

~~~java
public record ChangeOrderStatusCommand(
    String newStatus,
    long expectedVersion
) {}
~~~

Repository:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder>
        findByIdAndOrganizationId(
            Long id, Long organizationId);
}
~~~

Service:

~~~java
@Service
public class ChangeOrderStatusService {
    private final PurchaseOrderRepository repository;
    private final AuthorizationService authorization;

    public ChangeOrderStatusService(
            PurchaseOrderRepository repository,
            AuthorizationService authorization) {
        this.repository = repository;
        this.authorization = authorization;
    }

    @Transactional
    public void change(
            AuthenticatedUser actor,
            Long organizationId,
            Long orderId,
            ChangeOrderStatusCommand command) {

        authorization.requirePermission(
            actor, organizationId, "ORDER_UPDATE");

        PurchaseOrder order = repository
            .findByIdAndOrganizationId(
                orderId, organizationId)
            .orElseThrow(OrderNotFoundException::new);

        if (order.getVersion() != command.expectedVersion()) {
            throw new ConcurrentOrderModificationException();
        }

        order.changeStatus(command.newStatus());
    }
}
~~~

### 39.1. Tại sao không nhận entity detached?

Service chỉ nhận ý định thay đổi và version mong đợi. Nó tự tải entity hiện tại trong organization scope và kiểm tra quyền trước khi thay đổi.

### 39.2. Không cần repository.save sau setter

Order đã managed trong transaction. Dirty checking ghi thay đổi khi flush.

### 39.3. @Version vẫn cần thiết

So sánh expectedVersion ở service giúp phản hồi sớm; @Version ở entity bảo vệ race giữa lúc check và flush/commit.

## 40. Bài thực hành

### Bài A — Tái hiện lỗi merge result

1. Tạo một Order và persist.
2. Load rồi detach.
3. Gọi merge nhưng bỏ qua return value.
4. Sửa detached object.
5. Flush và đọc row bằng JDBC.
6. Chứng minh database chưa nhận thay đổi sau merge.
7. Sửa bằng cách dùng returned managed instance.

### Bài B — Kiểm tra entityManager.contains()

1. Assert entity managed sau find.
2. Detach và assert false.
3. Merge và giữ result.
4. Assert result managed, input detached.
5. Assert hai reference khác nhau.
6. Thử cùng ID đã tồn tại trong context và so sánh returned instance với instance đã load.

### Bài C — Spring Data save()

1. Test new entity để xác định persist path.
2. Test detached entity để xác định merge path.
3. Gọi save nhưng bỏ qua result.
4. Sửa input rồi flush.
5. Lặp lại với returned result.
6. Test entity dùng assigned UUID/Persistable nếu project có.

### Bài D — Cascade merge và collection

1. Tạo Order với Items.
2. Detach graph.
3. Thay đổi một child trên detached graph.
4. Merge và giữ managed result.
5. Thay đổi child trên managed graph.
6. Flush và JDBC verify.
7. Thử collection rỗng và orphanRemoval trong một test riêng.

### Bài E — Partial DTO update

1. Tạo Order đầy đủ field.
2. Nhận DTO chỉ có status.
3. Map DTO thành entity có ID và các field còn lại null.
4. Merge và quan sát nguy cơ null overwrite.
5. Viết lại service load-then-update.
6. Xác nhận các field ngoài command được giữ nguyên.

### Bài F — Optimistic locking

1. Tạo detached version 1.
2. Transaction khác cập nhật và commit version 2.
3. Merge detached version 1.
4. Xác nhận optimistic conflict.
5. Rollback transaction lỗi.
6. Reload state mới và xử lý command theo policy.

### Bài G — Security và tenant scope

1. Tạo Order thuộc organization 8.
2. Gửi detached object ID của Order đó từ user organization 7.
3. Thử merge trực tiếp và nhận diện lỗ hổng.
4. Thay bằng scoped repository query.
5. Xác nhận authorization trước update.
6. Test association Customer cũng phải cùng organization.

### Bài H — Transaction/SQL verification

1. Merge detached object.
2. Flush.
3. JDBC query cùng transaction.
4. Commit.
5. Mở transaction mới và đọc lại.
6. So sánh với case rollback.
7. Kiểm tra trigger/default/version nếu entity dùng.

## 41. Checklist trước khi gọi merge hoặc save

1. Object đầu vào đang new, managed hay detached?
2. Persistence context hiện tại là context nào?
3. Có entity cùng ID đã managed trong context không?
4. Đường đi save sẽ persist hay merge theo new detection?
5. Có giữ giá trị trả về của merge/save không?
6. Sau merge, mọi thay đổi tiếp theo có thao tác trên returned managed instance không?
7. Transaction còn mở khi sửa managed instance không?
8. Detached state có đầy đủ và authoritative không?
9. DTO có phân biệt omitted field và null không?
10. Collection có thể chưa load nhưng đang bị biểu diễn thành empty không?
11. Cascade MERGE có đúng ownership/lifecycle không?
12. Shared entities như Customer/Product/User có bị merge stale snapshot không?
13. Lazy associations có cần fetch trong transaction không?
14. Merge graph có thể gây N+1 hoặc load quá rộng không?
15. @Version có bảo vệ stale updates không?
16. Retry có tải state mới thay vì merge lại snapshot cũ không?
17. Authorization và organization scope được xác minh trước khi thay đổi không?
18. Bulk/native SQL có thể làm managed state stale không?
19. Database defaults/triggers có cần refresh hoặc SQL verification không?
20. Có test entityManager.contains và object identity không?
21. Có test JDBC/SQL độc lập xác nhận persisted row không?
22. Test có phân biệt flush với commit không?
23. Có test new detection của Spring Data khi ID được gán trước không?
24. Có test collection/orphan removal theo semantics thực tế không?

## 42. Tổng kết: merge trả về object cần tiếp tục sử dụng

~~~mermaid
flowchart TD
    A[Detached entity] --> B[EntityManager.merge]
    B --> C[Copy state]
    C --> D[Managed instance trong context]
    D --> E[Returned reference]
    E --> F[Tiếp tục sửa managed object]
    F --> G[Flush / commit]
    G --> H[Database row updated]
    B --> I[Source object vẫn detached]
    I --> J[Sửa source sau merge]
    J --> K[Không được dirty checking tự động]
~~~

Những nguyên tắc cần nhớ:

1. **merge() copy state; nó không reattach chính object nguồn.** Managed instance được trả về mới là object thuộc persistence context.
2. **Luôn giữ return value của EntityManager.merge() và Spring Data save()** khi thao tác tiếp sau đó.
3. **Sửa detached source sau merge không tự cập nhật managed target.** Đây là nguyên nhân trực tiếp của lỗi trong bài.
4. **Persist và merge khác nhau.** Persist làm new input managed; merge copy state vào managed instance.
5. **Entity đã managed thì dirty checking đủ để ghi thay đổi.** Không cần merge/save lại sau mỗi setter.
6. **Cascade MERGE có thể truyền state qua graph**, nhưng không làm các source child objects trở thành managed.
7. **Merge toàn graph có thể gây N+1, ghi đè dữ liệu mới và tác động collections/orphan removal.** Chỉ dùng khi detached graph có contract rõ.
8. **Entity từ HTTP/cache/message thường không phải command phù hợp.** Tải managed entity theo scope rồi áp dụng field updates được cho phép.
9. **@Version giúp phát hiện stale state**, nhưng không thay thế DTO semantics, authorization hoặc business conflict handling.
10. **Transaction kết thúc thì managed instance cũng có thể trở thành detached.** Đừng giữ reference rồi sửa ngoài transaction và mong dirty checking chạy.
11. **entityManager.contains() giúp kiểm tra lifecycle**, nhưng không chứng minh row đã commit.
12. **JDBC/SQL độc lập giúp xác nhận dữ liệu thực tế**, nhất là sau flush, bulk DML, trigger hoặc database-generated values.

Khi gọi merge, hãy xem object đầu vào như một nguồn state được chuyển vào persistence context. Sau lời gọi đó, mọi thao tác tiếp theo cần dùng **instance mà merge trả về**. Với các command chỉ thay đổi một vài thuộc tính, cách rõ ràng hơn thường là tải entity đang managed trong transaction, xác minh quyền và business rules, rồi sửa trực tiếp entity đó. Điều này tránh nhầm detached state với managed state và giảm nguy cơ ghi đè dữ liệu ngoài ý muốn.

# Gia nhập giao dịch JTA bằng joinTransaction khi phù hợp trong JPA

Trong Jakarta Persistence (JPA), việc một `EntityManager` đang tồn tại **không đồng nghĩa** nó đã tham gia vào giao dịch JTA hiện hành. Điều này đặc biệt quan trọng khi một persistence context được tạo **trước khi transaction bắt đầu**, hoặc được cấu hình **không đồng bộ với giao dịch** (*unsynchronized persistence context*).

Phương thức `EntityManager.joinTransaction()` cho phép yêu cầu một **JTA entity manager** liên kết persistence context của nó với **JTA transaction đang hoạt động**. Từ đó, các thay đổi đang được quản lý có thể được đồng bộ với database như một phần của transaction đó.

Bài học giải thích **khi nào cần, khi nào không cần và khi nào không nên gọi `joinTransaction()`**, cùng các quy tắc về `SynchronizationType.SYNCHRONIZED`, `UNSYNCHRONIZED`, `isJoinedToTransaction()`, `flush()` và `commit`. Trọng tâm là **gia nhập giao dịch JTA**, không phải tự tạo transaction mới hay thay thế transaction manager.

## 1. Ba trạng thái không nên đánh đồng

Khi viết code persistence, cần phân biệt ba câu hỏi:

1. **Đã có JTA transaction hoạt động hay chưa?** Transaction thường được tạo và kết thúc bởi container hoặc transaction manager.
2. **`EntityManager` có persistence context để quản lý entity hay chưa?** Persistence context chứa các entity managed và thông tin thay đổi đang chờ.
3. **Persistence context đó đã gia nhập JTA transaction hiện hành hay chưa?** Đây là điều `joinTransaction()` và `isJoinedToTransaction()` giải quyết.

~~~text
                  JTA transaction manager
                  begin / commit / rollback
                            |
                 Current JTA transaction
                            |
                (có thể tồn tại độc lập)
                            |
           EntityManager / persistence context
                /                      \
        Chưa join transaction      Đã join transaction
        --------------------       --------------------
        Có thể giữ managed data    Có thể flush các thay đổi
        Không đồng bộ tự động      thuộc transaction này
        theo transaction đó        khi flush/commit phù hợp
                \                      /
                 \-- joinTransaction()/
~~~

**`joinTransaction()` không tạo JTA transaction.** Nó chỉ có ý nghĩa khi đã có **transaction để tham gia**.

Ví dụ nhận định cần tránh:

~~~java
em.joinTransaction(); // Không tương đương với begin().
em.persist(order);
em.flush();           // Không tương đương commit().
~~~

Một transaction manager vẫn phải chịu trách nhiệm điều phối việc begin/commit/rollback của JTA transaction.

## 2. JTA khác RESOURCE_LOCAL ở điểm nào?

Trong JPA có hai mô hình quản lý transaction thường gặp.

| Đặc điểm | `RESOURCE_LOCAL` | `JTA` |
| --- | --- | --- |
| Ai quản lý giao dịch? | Ứng dụng qua `EntityTransaction` | JTA transaction manager/container/framework |
| Cách bắt đầu thường thấy | `em.getTransaction().begin()` | `@Transactional`, EJB transaction attribute hoặc `UserTransaction.begin()` |
| Cách commit | `em.getTransaction().commit()` | Transaction manager hoặc `UserTransaction.commit()` |
| `joinTransaction()` | Không phải cách quản lý resource-local | Dùng khi cần gia nhập một JTA transaction đang hoạt động |
| Cần nắm trạng thái tham gia? | Dựa vào `EntityTransaction` phù hợp | `em.isJoinedToTransaction()` |
| Khả năng phối hợp nhiều tài nguyên | Theo giới hạn giao dịch cục bộ | JTA có thể phối hợp các resource theo khả năng hệ thống |

Ví dụ resource-local:

~~~java
EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();
    em.persist(new PurchaseOrder("PO-1001"));
    em.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

Đây là luồng `RESOURCE_LOCAL`, **không phải ví dụ sử dụng `joinTransaction()`**.

Với JTA entity manager, không dùng `em.getTransaction().begin()` hoặc `em.getTransaction().commit()` để điều khiển transaction. Trên JTA entity manager, `getTransaction()` không phải API điều phối transaction phù hợp; sử dụng nó cho mục đích này có thể dẫn tới `IllegalStateException`.

### 2.1. JTA entity manager không đồng nghĩa luôn cần join thủ công

Khi dùng container-managed `EntityManager` mặc định **synchronized** trong transaction đã được container tạo, provider/container thường tự liên kết persistence context vào JTA transaction. Trong trường hợp đó, gọi `joinTransaction()` thủ công thường **không cần thiết**.

Ngược lại, khi dùng **unsynchronized persistence context** hoặc **JTA application-managed entity manager được tạo trước khi có transaction**, việc explicit join có thể là bước cần thiết.

Vì thế phải quyết định dựa trên **kiểu persistence context, cấu hình synchronization và thời điểm tạo/nhập transaction**, chứ không dùng công thức “JTA thì luôn gọi joinTransaction trước persist”.

## 3. API chuẩn: joinTransaction và isJoinedToTransaction

`EntityManager` cung cấp:

~~~java
void joinTransaction();

boolean isJoinedToTransaction();
~~~

Ví dụ:

~~~java
if (!em.isJoinedToTransaction()) {
    em.joinTransaction();
}
~~~

Điều kiện này chỉ có ý nghĩa khi **JTA transaction đã hoạt động** và `em` là JTA entity manager phù hợp. `isJoinedToTransaction() == false` không có nghĩa gọi `joinTransaction()` chắc chắn thành công, vì có thể **chưa có transaction hiện hành**.

### 3.1. joinTransaction thực sự làm gì?

Với JTA entity manager có persistence context chưa tham gia transaction, lời gọi:

~~~java
em.joinTransaction();
~~~

yêu cầu context tham gia **JTA transaction hiện hành**. Sau khi tham gia, các thay đổi entity managed có thể được đồng bộ qua `flush()` và trong quá trình hoàn tất transaction, theo hợp đồng JPA và cấu hình fetch/flush tương ứng.

Các đặc điểm cần nhớ:

- Không tạo transaction mới.
- Không commit hoặc rollback transaction.
- Không tự tải tất cả lazy collection.
- Không tự sinh ra các câu `INSERT` cho object chưa được `persist`.
- Không chuyển một entity detached thành managed.
- Không tự sửa quan hệ JPA bị khai báo sai.
- Có thể được gọi trên một entity manager đã tham gia transaction, nhưng thường không cần gọi lặp.

### 3.2. isJoinedToTransaction dùng để làm gì?

~~~java
boolean joined = em.isJoinedToTransaction();
~~~

Nó trả lời liệu entity manager **đang tham gia JTA transaction hiện hành** hay không. Đây không phải:

- Kiểm tra một transaction đã commit.
- Kiểm tra DB hiện có bao nhiêu row.
- Kiểm tra entity có được managed hay không.
- Kiểm tra SQL `INSERT` đã được thực thi hay chưa.
- Kiểm tra mọi thay đổi đều đã flush.
- Thay thế cho `EntityManager.contains(entity)`.

Bảng đối chiếu:

| Câu hỏi | API/cơ chế phù hợp |
| --- | --- |
| Entity manager đã join JTA transaction hiện hành chưa? | `em.isJoinedToTransaction()` |
| Yêu cầu JTA EM tham gia transaction hiện hành? | `em.joinTransaction()` |
| Entity có managed trong EM này không? | `em.contains(entity)` |
| Đồng bộ pending changes thành SQL trong transaction? | `em.flush()` |
| Commit hoặc rollback JTA transaction? | JTA transaction manager/container/`UserTransaction` |
| Có JTA transaction active hay không? | Transaction manager/JTA context, không suy từ việc có EM |
| Entity có thuộc tính LAZY đã tải chưa? | `PersistenceUnitUtil.isLoaded(...)` |

### 3.3. Nếu không có JTA transaction?

Nếu `joinTransaction()` được gọi khi **không có JTA transaction để gia nhập**, JPA có thể báo `TransactionRequiredException` theo hợp đồng của phương thức.

~~~java
// Không tạo transaction trước đó.
em.joinTransaction(); // Không dùng lời gọi này như "begin transaction".
~~~

Cách xử lý đúng là **mở transaction bằng transaction manager**, hoặc chuyển lời gọi sang phương thức/service đang chạy trong một transaction thích hợp. Không xử lý bằng cách gọi `em.joinTransaction()` liên tục cho tới khi thành công.

## 4. SYNCHRONIZED và UNSYNCHRONIZED: lựa chọn quyết định

Từ JPA 2.1, `SynchronizationType` cho phép phân biệt hai kiểu đồng bộ của persistence context với JTA transaction.

~~~java
import jakarta.persistence.SynchronizationType;
~~~

### 4.1. SYNCHRONIZED: trường hợp thông thường

~~~java
@PersistenceContext(
    unitName = "shopPU",
    synchronization = SynchronizationType.SYNCHRONIZED
)
private EntityManager em;
~~~

`SYNCHRONIZED` là cấu hình thông thường/mặc định. Khi persistence context gắn với transaction thích hợp, provider/container đồng bộ nó với transaction theo quy tắc JPA.

Ở ứng dụng Jakarta EE dùng container-managed transaction:

~~~java
import jakarta.ejb.Stateless;
import jakarta.ejb.TransactionAttribute;
import jakarta.ejb.TransactionAttributeType;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

@Stateless
public class OrderService {

    @PersistenceContext(unitName = "shopPU")
    private EntityManager em;

    @TransactionAttribute(TransactionAttributeType.REQUIRED)
    public void createOrder(String code) {
        // Container cung cấp transaction phù hợp.
        em.persist(new PurchaseOrder(code));

        // Thường không cần:
        // em.joinTransaction();
    }
}
~~~

Ở đây:

- Transaction `REQUIRED` thường được container mở hoặc sử dụng transaction đang có.
- Context được đồng bộ với transaction theo cơ chế container-managed mặc định.
- `em.persist(...)` quản lý entity mới.
- Khi method hoàn tất thành công theo quy tắc EJB, container điều phối commit.
- Không cần `EntityTransaction.commit()` trong method.

Điều cần đánh giá không phải “tôi đã gọi joinTransaction chưa”, mà là “entity manager và transaction manager có đang cấu hình phù hợp, và transaction nào đang chứa thao tác persistence?”.

### 4.2. UNSYNCHRONIZED: không tự tham gia transaction

~~~java
@PersistenceContext(
    unitName = "shopPU",
    synchronization = SynchronizationType.UNSYNCHRONIZED
)
private EntityManager em;
~~~

Với `UNSYNCHRONIZED`, persistence context không tự động đồng bộ với JTA transaction hiện hành theo cách của synchronized context. Ứng dụng phải **yêu cầu gia nhập một cách tường minh** vào transaction khi muốn các thay đổi của context được ghi như một phần của giao dịch đó.

~~~java
em.joinTransaction();
~~~

Sau khi join, có thể gọi `flush` khi transaction còn hợp lệ hoặc để quy trình giao dịch thực hiện đồng bộ phù hợp.

| Cấu hình | Tham gia JTA transaction | Khi nào thường dùng |
| --- | --- | --- |
| `SYNCHRONIZED` | Tự động theo quy tắc JPA/container trong ngữ cảnh phù hợp | Service CRUD thông thường |
| `UNSYNCHRONIZED` | Không tự động; cần explicit `joinTransaction()` khi muốn ghi | Quy trình giữ trạng thái qua nhiều bước hoặc chủ động chọn thời điểm đồng bộ |

**UNSYNCHRONIZED không có nghĩa “database tự đồng bộ khi có commit”.** Nếu context chưa join transaction, không nên kỳ vọng pending changes của nó được flush chỉ vì một transaction bên ngoài được commit.

## 5. Ví dụ chính: JTA UNSYNCHRONIZED và explicit joinTransaction

Giả sử entity `PurchaseOrder`:

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(name = "order_code", nullable = false, unique = true)
    private String orderCode;

    @Column(name = "status", nullable = false)
    private String status = "DRAFT";

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String orderCode) {
        this.orderCode = orderCode;
    }

    public Long getId() {
        return id;
    }

    public String getOrderCode() {
        return orderCode;
    }

    public void confirm() {
        this.status = "CONFIRMED";
    }
}
~~~

Trong Jakarta EE EJB, inject `EntityManager` theo chế độ unsynchronized:

~~~java
package com.example.shop.application;

import com.example.shop.domain.PurchaseOrder;
import jakarta.ejb.Stateless;
import jakarta.ejb.TransactionAttribute;
import jakarta.ejb.TransactionAttributeType;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.SynchronizationType;

@Stateless
public class ExplicitJoinOrderService {

    @PersistenceContext(
        unitName = "shopPU",
        synchronization = SynchronizationType.UNSYNCHRONIZED
    )
    private EntityManager em;

    @TransactionAttribute(TransactionAttributeType.REQUIRED)
    public Long createOrder(String code) {
        // EJB container đã tạo hoặc tham gia một JTA transaction.
        // UNSYNCHRONIZED cần được yêu cầu join rõ ràng.
        em.joinTransaction();

        PurchaseOrder order = new PurchaseOrder(code);
        em.persist(order);

        // Flush tùy chọn: chỉ cần khi có lý do kiểm tra SQL sớm.
        em.flush();

        return order.getId();
        // Container commit sau khi method kết thúc hợp lệ.
    }
}
~~~

Các mốc thực hiện:

1. Container bắt đầu hoặc tiếp nhận transaction cho `createOrder`.
2. Entity manager chưa tự join vì `SynchronizationType.UNSYNCHRONIZED`.
3. `em.joinTransaction()` liên kết persistence context với transaction hiện hành.
4. `persist` đưa entity mới vào trạng thái managed.
5. `flush` (nếu gọi) đồng bộ thay đổi thành SQL **trong transaction**, không commit.
6. Khi phương thức hoàn tất, container quyết định commit/rollback theo quy tắc transaction.

Dòng `em.joinTransaction()` nằm **bên trong** phương thức có transaction active. Nếu gọi nó trong một phương thức không có transaction, việc gia nhập không có đích và có thể phát sinh `TransactionRequiredException`.

### 5.1. Thứ tự join và persist có bắt buộc như nhau không?

Trong ví dụ chính, ta **join trước khi persist** để minh họa luồng ghi dễ hiểu. Tuy nhiên, mục đích của unsynchronized persistence context là cho phép giữ một số thay đổi trạng thái **chưa tham gia transaction** để chờ thời điểm đồng bộ thích hợp.

Một luồng concept có thể là:

~~~text
Tạo / thao tác managed entities trong unsynchronized context
                    |
                    | Chưa tự đồng bộ xuống DB
                    v
       Có JTA transaction phù hợp
                    |
                    | em.joinTransaction()
                    v
        Context được tham gia transaction
                    |
                    | em.flush() hoặc flush khi commit
                    v
           SQL trong JTA transaction
                    |
                    v
             Commit / rollback
~~~

Không suy diễn rằng bất cứ hoạt động ghi nào ngoài transaction cũng phù hợp trong mọi loại persistence context. Những thao tác được phép, thời gian sống entity và cách duy trì context phụ thuộc **transaction-scoped hay extended**, kiểu đồng bộ và quy tắc JPA. Ví dụ ở mục tiếp theo làm rõ trường hợp extended context.

## 6. Extended persistence context: giữ trạng thái qua nhiều bước

Một ví dụ điển hình cho explicit join là **extended persistence context** trong một stateful session bean. Context extended có thể sống qua nhiều lần gọi business method thay vì kết thúc cùng một transaction ngắn.

Giả sử người dùng tạo bản nháp cấu hình đơn hàng qua nhiều màn hình; chưa muốn ghi database cho tới khi nhấn “Xác nhận”.

~~~text
Bước 1: tạo bản nháp         Không JTA transaction
             |
Bước 2: sửa chi tiết         Không JTA transaction
             |
Bước 3: xác nhận             JTA transaction bắt đầu
             |
             +-- joinTransaction()
             +-- flush
             +-- commit do container thực hiện
~~~

### 6.1. Bean với extended UNSYNCHRONIZED context

~~~java
package com.example.shop.application;

import com.example.shop.domain.PurchaseOrder;
import jakarta.ejb.Stateful;
import jakarta.ejb.TransactionAttribute;
import jakarta.ejb.TransactionAttributeType;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.PersistenceContextType;
import jakarta.persistence.SynchronizationType;

@Stateful
public class OrderDraftConversation {

    @PersistenceContext(
        unitName = "shopPU",
        type = PersistenceContextType.EXTENDED,
        synchronization = SynchronizationType.UNSYNCHRONIZED
    )
    private EntityManager em;

    private PurchaseOrder draft;

    @TransactionAttribute(TransactionAttributeType.NOT_SUPPORTED)
    public void startDraft(String code) {
        draft = new PurchaseOrder(code);
        em.persist(draft);
        // Giữ entity trong extended context; chưa join JTA transaction.
    }

    @TransactionAttribute(TransactionAttributeType.NOT_SUPPORTED)
    public void confirmDraftInMemory() {
        if (draft == null) {
            throw new IllegalStateException("Draft not started");
        }
        draft.confirm();
        // Sửa managed entity trong extended context.
    }

    @TransactionAttribute(TransactionAttributeType.REQUIRED)
    public Long publishDraft() {
        if (draft == null) {
            throw new IllegalStateException("Draft not started");
        }

        em.joinTransaction();
        em.flush();

        return draft.getId();
        // Transaction do container commit khi hoàn tất.
    }
}
~~~

Ví dụ này minh họa ý tưởng **tạo và cập nhật trạng thái trong extended unsynchronized context trước khi join**. Việc thực hiện ngoài transaction phù hợp với mô hình unsynchronized extended persistence context, nhưng cần hiểu các giới hạn:

- **Không gọi `flush()` trước khi context tham gia một transaction thích hợp.**
- Những thay đổi chưa join/flush **chưa phải dữ liệu đã commit**.
- `@GeneratedValue` và cách cấp ID có thể khiến việc nhận ID xảy ra ở các mốc khác nhau tùy generator/provider.
- Stateful bean có vòng đời, concurrency và cơ chế hủy riêng; không nên dùng dài hạn vô hạn hoặc chia sẻ giữa nhiều người dùng.
- Nếu người dùng bỏ bản nháp, cần có chính sách kết thúc cuộc hội thoại và giải phóng context, không chỉ quên tham chiếu `draft`.

**Đặc biệt quan trọng:** nếu một extended context đã join một transaction và transaction đó commit, không nên giả định nó trở lại trạng thái unsynchronized như lúc mới tạo. Khi thiết kế nhiều transaction tiếp nối, phải tuân theo quy tắc synchronization và vòng đời của context; có thể cần tạo context mới cho một chu kỳ làm việc mới. Không dùng ví dụ này như cơ chế “điều khiển đóng/mở tự do” một context đang sống qua nhiều transaction.

### 6.2. Khi nào extended context không phải lựa chọn tốt?

Không phải cứ có nhiều bước UI là phải giữ một `EntityManager` qua nhiều request. Các hạn chế:

- Context giữ nhiều managed entity có thể tăng sử dụng bộ nhớ.
- Dữ liệu được giữ lâu có thể lỗi thời so với database.
- Người dùng có thể bỏ thao tác, làm bản nháp không được giải phóng kịp.
- Cạnh tranh cập nhật vẫn cần optimistic locking hoặc kiểm tra phiên bản.
- Stateless REST service và môi trường scale-out thường dễ kiểm soát hơn với DTO/bản nháp tách riêng.

Nhiều hệ thống chọn **DTO draft + transaction ngắn ở bước cuối**, hoặc lưu bản nháp riêng như một trạng thái nghiệp vụ. Extended unsynchronized context là công cụ đặc biệt, không phải mặc định cho mọi workflow.

## 7. JTA application-managed EntityManager tạo ngoài transaction

Không chỉ container-managed entity manager mới có thể cần `joinTransaction()`. Một `EntityManager` được tạo bằng `EntityManagerFactory` cho một **JTA persistence unit** có thể được tạo **khi chưa có JTA transaction**.

Ví dụ tình huống:

~~~text
T0: emf.createEntityManager()      (chưa có JTA transaction)
    |
T1: một service bắt đầu JTA transaction
    |
T2: sử dụng EntityManager đã tạo từ T0
    |
    +-- joinTransaction() nếu context chưa tham gia
    |
T3: persist/flush trong transaction
    |
T4: transaction manager commit
~~~

Các bước này chỉ an toàn khi entity manager được sử dụng đúng phạm vi, **không chia sẻ giữa các thread**, và transaction JTA thực sự active ở thời điểm join.

### 7.1. Tạo JTA EntityManager với SynchronizationType

Ở JPA 2.1+ (Jakarta Persistence 3.x), có overload cho việc tạo application-managed entity manager:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.SynchronizationType;

EntityManager em = emf.createEntityManager(
    SynchronizationType.UNSYNCHRONIZED
);
~~~

Cách này cho biết rõ context không tự đồng bộ với JTA transaction. Khi transaction được mở bởi JTA manager:

~~~java
// Pseudocode cho phần đã nằm trong JTA transaction hoạt động:
if (!em.isJoinedToTransaction()) {
    em.joinTransaction();
}

em.persist(new PurchaseOrder("PO-1002"));
em.flush();
~~~

Đoạn này không tự mở transaction; phần code điều phối JTA không được thể hiện. Không gọi trong service không có transaction rồi cho rằng `joinTransaction` sẽ tạo transaction.

Đối với application-managed entity manager, ứng dụng cũng có trách nhiệm gọi `em.close()` khi hoàn tất vòng đời của nó. Không lấy một entity manager application-managed rồi giữ ở singleton cho nhiều request/thread để tiết kiệm khởi tạo: `EntityManager` không được thiết kế để dùng đồng thời giữa các thread.

### 7.2. Trường hợp synchronized EntityManager tạo ngoài transaction

Một JTA application-managed `EntityManager` mặc định synchronized được tạo ngoài transaction không nhất thiết đã được gắn với **một JTA transaction chưa tồn tại**. Khi sau đó một transaction trở nên active, `joinTransaction()` có thể được dùng để yêu cầu entity manager đó gia nhập transaction hiện hành.

Điều khác với container-managed synchronized context tạo/sử dụng trong transaction là **thời điểm và cơ chế enlistment**. Không dựa hoàn toàn vào annotation hoặc chữ “synchronized” để bỏ qua nhu cầu kiểm tra tham gia giao dịch của một application-managed entity manager đã tồn tại qua các ranh giới khác nhau.

## 8. @Transactional của Spring và Jakarta EE: khi nào không cần join thủ công?

### 8.1. Spring Data JPA CRUD thông thường

Trong ứng dụng Spring Boot dùng JPA và transaction manager được cấu hình phù hợp:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository repository;

    public OrderApplicationService(
            PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void create(String code) {
        repository.save(new PurchaseOrder(code));
    }
}
~~~

Ở code thường ngày như trên, transaction manager và repository/entity manager tích hợp đã đảm nhận việc tham gia transaction thích hợp. **Không cần thêm `joinTransaction()`** chỉ vì đây là JPA.

Lưu ý:

- `@Transactional` của Spring là API framework và có thể làm việc với `JpaTransactionManager` (resource-local theo mô hình phù hợp) hoặc `JtaTransactionManager` (JTA).
- Không thể suy luận việc một method có `@Transactional` tức là đang dùng JTA; phải xem transaction manager/persistence unit thực tế.
- `repository.save(...)` không đồng nghĩa transaction đã commit ngay tại dòng đó; commit thường xảy ra khi interceptor transaction kết thúc method hợp lệ.
- Nếu đang dùng Spring và một custom JTA application-managed/unsynchronized entity manager nằm ngoài cơ chế tích hợp thông thường, có thể vẫn cần explicit join — dựa vào ngữ cảnh thật, không theo thói quen.

### 8.2. Jakarta EE/CDI @Transactional

Trong Jakarta EE:

~~~java
import jakarta.inject.Inject;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.transaction.Transactional;

@Transactional
public class OrderFacade {

    @PersistenceContext(unitName = "shopPU")
    private EntityManager em;

    public void create(String code) {
        em.persist(new PurchaseOrder(code));
    }
}
~~~

Ở đây, `@Transactional` thuộc `jakarta.transaction`, cung cấp ranh giới giao dịch qua cơ chế container. Với injected synchronized entity manager trong mô hình thông thường, provider/container xử lý sự tham gia vào transaction.

Nếu dùng:

~~~java
@PersistenceContext(
    unitName = "shopPU",
    synchronization = SynchronizationType.UNSYNCHRONIZED
)
private EntityManager em;
~~~

thì phải chủ động xem xét explicit `joinTransaction()` **bên trong transaction** trước khi muốn các thay đổi được đồng bộ. Điều đó không có nghĩa mọi method chỉ đọc cũng cần join, hoặc cứ inject unsynchronized là phải join ngay tại constructor.

### 8.3. @Transactional không bảo đảm transaction nếu gọi sai đường

Với Spring dùng proxy interception thông thường, một method `@Transactional` được gọi bằng `this.someMethod()` từ chính instance có thể không đi qua proxy, khiến transaction không được tạo như kỳ vọng.

Khi gặp `TransactionRequiredException` ở `joinTransaction()`, cần kiểm tra **transaction thực sự active hay không**, không chỉ nhìn thấy một annotation `@Transactional` trong mã nguồn.

## 9. Cấu hình persistence unit JTA

Một persistence unit dùng JTA thường khai báo transaction type và JTA datasource phù hợp:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="shopPU" transaction-type="JTA">
        <jta-data-source>
            java:comp/env/jdbc/ShopDS
        </jta-data-source>

        <class>com.example.shop.domain.PurchaseOrder</class>
    </persistence-unit>
</persistence>
~~~

Đây là cấu hình minh họa cho Jakarta Persistence 3.1 trong môi trường có datasource JTA được container cung cấp. Tên JNDI và setup tài nguyên thật tùy server.

Cần phân biệt:

- `transaction-type="JTA"`: persistence unit tham gia quản lý transaction theo JTA.
- `jta-data-source`: tài nguyên kết nối có khả năng tham gia transaction JTA theo cấu hình.
- `@PersistenceContext` hoặc `emf.createEntityManager(...)`: quyết định cách tạo và quản lý entity manager/persistence context.
- `SynchronizationType`: quyết định sự đồng bộ tự động hay cần explicit join.
- `joinTransaction()`: thao tác gia nhập **transaction hiện hành**, không thay thế các phần cấu hình trên.

Nếu dữ liệu được tạo trong một persistence unit `RESOURCE_LOCAL` nhưng code lại giả định có thể dùng `joinTransaction()` thay cho `EntityTransaction.begin()`, đó là dấu hiệu nhầm lẫn giữa hai mô hình. Không sửa bằng cách thêm `joinTransaction()` vào mọi repository; cần chọn đúng transaction strategy.

## 10. joinTransaction, persist, flush và commit khác nhau thế nào?

Đây là sơ đồ then chốt:

~~~text
JTA transaction manager:
    BEGIN JTA TRANSACTION
        |
        v
Persistence context (UNSYNCHRONIZED):
    [chưa joined]
        |
        | EntityManager.joinTransaction()
        v
    [joined current JTA transaction]
        |
        | EntityManager.persist(newEntity)
        v
    [entity được quản lý, pending changes]
        |
        | EntityManager.flush()
        v
    [INSERT / UPDATE / DELETE trong JTA transaction]
        |
        | JTA transaction manager COMMIT
        v
    [các thay đổi đã commit nếu thành công]
~~~

Bảng đối chiếu:

| Hoạt động | Tác động | Có mở transaction? | Có commit? |
| --- | --- | --- | --- |
| `joinTransaction()` | Liên kết context với JTA transaction active | Không | Không |
| `persist(entity)` | Đưa entity mới vào managed state | Không | Không |
| `flush()` | Đồng bộ pending changes thành SQL | Không | Không |
| JTA `commit` | Hoàn tất transaction qua manager/container | Transaction đã được mở từ trước | **Có** |
| JTA `rollback` | Hủy những thay đổi chưa commit thuộc transaction | Không | Không; kết thúc theo rollback |

Một transaction có thể bao gồm nhiều thao tác JPA và nhiều resource; `joinTransaction` chỉ xử lý **mối liên hệ của persistence context với transaction hiện tại**.

### 10.1. Nếu đã join, gọi flush có được không?

Khi JTA transaction active và context đã joined, `em.flush()` có thể đồng bộ thay đổi pending phù hợp, ví dụ để phát hiện constraint sớm:

~~~java
em.joinTransaction();
em.persist(new PurchaseOrder("PO-1003"));
em.flush();
~~~

`flush()` không bảo đảm commit sẽ thành công: có thể còn deferred constraints hoặc lỗi transaction về sau. Nó cũng không tự sinh transaction nếu chưa có.

### 10.2. Nếu chưa join, có flush được không?

Với unsynchronized context chưa joined, **không được sử dụng `flush()` như cách tự gia nhập transaction**. JPA có thể ném `TransactionRequiredException` nếu context không tham gia transaction hợp lệ.

~~~java
// Trong UNSYNCHRONIZED context nhưng chưa join:
em.flush(); // Không phải cách thay thế em.joinTransaction().
~~~

Cần có JTA transaction active rồi gọi explicit join trước khi yêu cầu flush.

### 10.3. Commit JTA có tự flush một unsynchronized context chưa joined?

Không nên kỳ vọng. Nếu context chưa gia nhập JTA transaction, những thay đổi đang chờ trong đó **không được tự động đồng bộ như một phần của transaction** chỉ vì transaction manager commit.

Đây là lý do `UNSYNCHRONIZED` có ý nghĩa: ứng dụng kiểm soát thời điểm context tham gia transaction. Nhưng quyền kiểm soát đó đi kèm trách nhiệm gọi `joinTransaction()` ở thời điểm nghiệp vụ cần lưu thay đổi.

## 11. Lưu ý về truy vấn trước khi gia nhập transaction

Một unsynchronized persistence context có thể chứa các entity managed, trong khi những thay đổi của chúng chưa được gửi xuống DB. Nếu thực hiện JPQL trước `joinTransaction()`, không được mặc định kết quả truy vấn database phản ánh toàn bộ thay đổi pending của context.

Ví dụ:

~~~java
// Bối cảnh: extended unsynchronized context đang giữ một bản nháp.
em.persist(new PurchaseOrder("DRAFT-001"));

// Một truy vấn COUNT ở thời điểm này không phải bằng chứng
// bản nháp đã được flush/commit.
Long count = em.createQuery(
    """
    SELECT COUNT(o)
    FROM PurchaseOrder o
    WHERE o.orderCode = :code
    """,
    Long.class
)
.setParameter("code", "DRAFT-001")
.getSingleResult();
~~~

Nếu nghiệp vụ cần query nhìn thấy các thay đổi pending như một phần giao dịch, hãy có JTA transaction phù hợp, join context rồi áp dụng cơ chế flush/fetch nhất quán. Đừng dùng kết quả COUNT trước khi join như bằng chứng đơn hàng đã được lưu.

Ngược lại, gọi `joinTransaction()` không có nghĩa tự động tải mọi quan hệ LAZY hoặc refresh mọi entity. Trạng thái managed và trạng thái load của từng thuộc tính vẫn là các vấn đề riêng.

## 12. EntityManager tham gia transaction nhưng entity đã detached

Một nhầm lẫn phổ biến:

~~~java
// Entity đã detached vì được tạo từ EM khác hoặc context cũ.
PurchaseOrder detached = previouslyLoadedOrder;

em.joinTransaction();

// Không có nghĩa detached lập tức trở thành managed:
boolean managed = em.contains(detached);
~~~

`joinTransaction` điều chỉnh **persistence context và JTA transaction**, không điều chỉnh lifecycle của một object detached bất kỳ.

Muốn cập nhật detached state theo cách phù hợp:

~~~java
PurchaseOrder managed = em.merge(detached);
managed.confirm();
~~~

`merge` trả về managed instance; không nên tự khẳng định biến `detached` cũ đã trở thành managed. Việc merge có thể phát sinh SQL theo ngữ nghĩa provider, và các xung đột phiên bản phải được xử lý qua transaction.

### 12.1. Persistence context không phải chính transaction

Một extended persistence context có thể sống **qua nhiều transaction**. Ngược lại, transaction-scoped context thường gắn với một transaction cụ thể.

| Khái niệm | Phạm vi |
| --- | --- |
| Entity instance | Java object |
| Persistence context | Tập entity managed và trạng thái ORM theo một phạm vi |
| EntityManager | API truy cập/quản lý persistence context |
| JTA transaction | Ranh giới atomicity của các thao tác tài nguyên |
| `joinTransaction()` | Kết nối persistence context với transaction active |
| `commit` | Hoàn tất transaction ở transaction manager |

Không gọi `joinTransaction()` chỉ vì một managed entity có `id != null`. Entity có ID không đồng nghĩa database đã commit, càng không chứng minh context đang joined.

## 13. Thời điểm join và thời điểm cấp ID

Chiến lược sinh khóa có ảnh hưởng đến SQL thực thi trước hoặc sau khi gia nhập JTA transaction.

### 13.1. Sequence

~~~java
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE)
private Long id;
~~~

Provider có thể lấy giá trị sequence khi chuẩn bị lưu entity. Giá trị ID xuất hiện không chứng minh `INSERT` đã được flush hoặc transaction đã commit.

### 13.2. Identity

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Với `IDENTITY`, database thường cấp ID ở `INSERT`. Khi entity manager chưa joined và chưa có transaction để ghi, hành vi cấp ID có thể phải chờ tới thời điểm đủ điều kiện thực thi SQL. Không thiết kế workflow unsynchronized dựa vào việc `id` chắc chắn có ngay sau `persist` với mọi generator.

### 13.3. Assigned ID/UUID

Nếu ứng dụng tạo UUID trước:

~~~java
UUID id = UUID.randomUUID();
PurchaseOrder order = new PurchaseOrder(id, "DRAFT-002");
~~~

thì entity có định danh trước khi gia nhập transaction. Tuy nhiên ID được cấp trước **không có nghĩa bản ghi tồn tại trong DB**. Đây là lựa chọn có thể hữu ích cho workflow bản nháp, nhưng vẫn phải thiết kế đúng chiến lược persist/merge và xử lý va chạm khóa.

**Nguyên tắc:** `joinTransaction()` không phải “lấy ID” và cũng không phải “cam kết đã có ID trong database”.

## 14. Quan hệ giữa joinTransaction và rollback

Giả sử một unsynchronized context được join và flush trong JTA transaction:

~~~java
em.joinTransaction();
em.persist(new PurchaseOrder("PO-1004"));
em.flush();

// Sau đó transaction manager quyết định ROLLBACK.
~~~

SQL đã chạy nhưng chưa commit có thể bị database rollback cùng transaction. Điều này cho thấy:

- `joinTransaction` không đảm bảo dữ liệu được commit.
- `flush` cũng không đảm bảo dữ liệu được commit.
- `rollback` hủy các thay đổi transactional chưa commit.
- Giá trị sequence đã cấp có thể không được thu hồi.
- Những external side effect (email, HTTP request) ngoài transaction không tự rollback.

Sau lỗi khiến transaction rollback-only, không nên tiếp tục flush một cách tùy tiện trên cùng transaction. Cần để transaction manager rollback và quản lý lại trạng thái persistence context đúng theo mô hình ứng dụng.

### 14.1. Extended context sau rollback

Một extended context có thể vẫn tồn tại sau một transaction bị rollback, nhưng trạng thái các managed entity và sự phù hợp để dùng tiếp không thể xem như thể transaction chưa từng xảy ra. Tùy môi trường, các thay đổi đang giữ có thể không tương ứng với DB sau rollback.

Nếu workflow cần tiếp tục, phải xác định quy tắc làm mới/loại bỏ bản nháp, xử lý phiên bản và vòng đời context. Không suy rằng “rollback đã hủy SQL nên mọi object trong extended context tự trở lại giá trị trước khi sửa”.

## 15. Giao dịch nhiều resource và JTA

Một lợi ích của JTA là một transaction manager có thể điều phối các tài nguyên tham gia giao dịch theo khả năng môi trường. Ví dụ:

~~~text
             JTA Transaction
                  /     \
                 /       \
        Database A       Database B
          (JPA PU1)        (JPA PU2)
                 \       /
                  \     /
              Transaction manager
             commit / rollback
~~~

Nếu có hai JTA entity managers thuộc hai persistence units, chúng cần được tích hợp đúng với JTA transaction manager và tài nguyên được hỗ trợ. `joinTransaction()` có thể là một bước cần thiết cho entity manager chưa tham gia transaction, nhưng **không tự biến các kết nối thông thường thành XA resource**.

JTA còn phải chịu các điều kiện:

- Datasource/driver có khả năng enlistment phù hợp.
- Transaction manager và cấu hình resource đúng.
- Provider kết nối entity managers vào transaction đúng cách.
- Các lỗi prepare/commit hoặc heuristic outcome được xử lý phù hợp nếu sử dụng cơ chế phối hợp phân tán.

Do đó, không nên nghĩ chỉ cần gọi `joinTransaction()` trên hai entity manager là có giao dịch phân tán atomic tuyệt đối. Nó giải quyết **khâu tham gia transaction của persistence context**, không thay thế năng lực của hạ tầng JTA.

## 16. EntityManager không thread-safe; tránh dùng lại tùy tiện

Một entity manager không được dùng chung đồng thời giữa nhiều thread. Trong ứng dụng web, tuyệt đối không giữ một application-managed `EntityManager` như trường singleton rồi gọi `joinTransaction()` cho nhiều request khác nhau.

Ví dụ ý tưởng sai:

~~~java
@ApplicationScoped
public class WrongSharedManager {

    private EntityManager sharedEm; // Không chia sẻ EM giữa request/thread.

    public void handleRequest() {
        sharedEm.joinTransaction();
        // ...
    }
}
~~~

Thay vào đó:

- Dùng container-managed `@PersistenceContext` theo cách container hỗ trợ, hoặc
- Tạo application-managed `EntityManager` theo phạm vi một thao tác/transaction, đóng khi hoàn tất, hoặc
- Dùng extended context theo đúng vòng đời của một conversation/session khi có lý do nghiệp vụ rõ.

Có được reference tới `EntityManagerFactory` để tạo nhiều EM là chuyện khác: factory được thiết kế để tái sử dụng, còn mỗi `EntityManager` phải được sử dụng đúng ranh giới và thread.

## 17. Các lỗi thường gặp và nguyên nhân

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `joinTransaction()` ném `TransactionRequiredException` | Không có JTA transaction active khi gọi | Tạo transaction bằng container/transaction manager trước; không dùng join như begin |
| `flush()` báo chưa có transaction | Context chưa joined hoặc không có transaction | Kiểm tra JTA active và `isJoinedToTransaction()` |
| Commit nhưng dữ liệu của unsynchronized context không được ghi | Context chưa join transaction | Explicit join tại thời điểm ghi trước flush/commit |
| Dùng `getTransaction().begin()` trên JTA EM | Nhầm JTA với RESOURCE_LOCAL | Để JTA manager/container điều phối transaction |
| Gọi join trong mọi repository method | Không hiểu context synchronized đã auto join | Chỉ gọi khi thực sự cần, đặc biệt unsynchronized/context tạo ngoài transaction |
| `isJoinedToTransaction() == false` rồi join vẫn lỗi | Không có transaction hiện hành hoặc context không phù hợp | Kiểm tra transaction manager và ranh giới method |
| Có `@Transactional` nhưng không có transaction khi chạy | Cấu hình/proxy/transaction manager chưa thực sự kích hoạt | Kiểm tra cơ chế interception, datasource và context |
| Entity detached vẫn không update sau join | Join không làm detached entity thành managed | Dùng `find`/`merge` hoặc thiết kế lại lifecycle |
| `persist` có ID nhưng row chưa có trong DB | ID sinh trước INSERT/flush/commit | Không dùng ID làm bằng chứng đã commit |
| `flush` chạy nhưng sau đó không thấy dữ liệu | Transaction rollback | Kiểm tra outcome commit và rollback-only |
| Extended context giữ dữ liệu cũ | Context sống lâu qua nhiều transaction | Thiết kế refresh/concurrency và vòng đời context |
| SQL trước join không thấy pending changes | Context chưa synchronized với transaction | Join/flush trong transaction hoặc dùng fetch plan phù hợp |
| Dùng `joinTransaction` để giải quyết N+1 | Nhầm transaction enlistment với lazy loading | Thiết kế fetch join, entity graph, batch fetch |
| Dùng cùng EM trên nhiều thread | EntityManager không thread-safe | Tạo context đúng phạm vi hoặc container-managed |
| JTA nhiều DB không atomic như mong đợi | Hạ tầng resource/transaction manager không hỗ trợ đúng | Kiểm tra XA/enlistment và cấu hình phân tán |

## 18. Chẩn đoán bằng các câu hỏi có thứ tự

Khi gặp lỗi về `joinTransaction` hoặc flush, cần trả lời các câu hỏi sau trước khi thay annotation:

1. Persistence unit đang dùng `transaction-type="JTA"` hay `RESOURCE_LOCAL`?
2. `EntityManager` được container inject hay do `EntityManagerFactory` tạo?
3. Persistence context là `TRANSACTION` hay `EXTENDED`?
4. Synchronization mode là `SYNCHRONIZED` hay `UNSYNCHRONIZED`?
5. Tại thời điểm gọi `joinTransaction()` có **JTA transaction active** thật không?
6. `em.isJoinedToTransaction()` trả gì trong đúng method/context đó?
7. Việc cần làm là **persist**, **flush**, **query**, hay **commit**? Có đang lẫn trách nhiệm không?
8. Transaction manager có đặt giao dịch thành rollback-only sau lỗi trước đó không?
9. Entity đang managed hay detached?
10. SQL log cho thấy các thay đổi được đồng bộ lúc nào và transaction kết thúc thế nào?

Sơ đồ quyết định:

~~~text
                Cần ghi thay đổi bằng JPA?
                            |
                            v
                Persistence unit kiểu gì?
                     /              \
             RESOURCE_LOCAL          JTA
                 |                    |
                 v                    v
      EntityTransaction        JTA transaction active?
      begin / commit              /          \
                                Không          Có
                                  |            |
                                  v            v
                         Tạo transaction   EM đã joined?
                         bằng manager       /      \
                                         Có         Không
                                          |           |
                                          v           v
                                      persist/     Context có cần
                                      flush        explicit join?
                                                  /          \
                                               Không          Có
                                                 |             |
                                                 v             v
                                           Auto join theo  joinTransaction()
                                           cấu hình        |
                                                 \         /
                                                  \       /
                                                   v     v
                                                    persist/
                                                    flush
                                                       |
                                                       v
                                             JTA manager commit
~~~

Không dùng sơ đồ này để “join cho chắc” ngay cả khi không có transaction. **Transaction phải tồn tại trước; join chỉ là bước tham gia khi cần.**

## 19. Thực hành: chọn phương án phù hợp

### Bài 1. @PersistenceContext mặc định trong EJB

~~~java
@Stateless
public class PaymentService {
    @PersistenceContext
    EntityManager em;

    @TransactionAttribute(TransactionAttributeType.REQUIRED)
    public void pay(Payment payment) {
        em.persist(payment);
    }
}
~~~

**Hỏi:** Có bắt buộc gọi `em.joinTransaction()` không?

**Đáp án:** Không trong cấu hình container-managed synchronized thông thường. Context tham gia transaction theo cơ chế container/JPA. Chỉ thêm explicit join khi có lý do cụ thể, không làm như một thủ tục bắt buộc của mọi service.

### Bài 2. UNSYNCHRONIZED trong JTA transaction

~~~java
@PersistenceContext(
    synchronization = SynchronizationType.UNSYNCHRONIZED
)
EntityManager em;

@TransactionAttribute(TransactionAttributeType.REQUIRED)
public void save(String code) {
    em.persist(new PurchaseOrder(code));
    em.flush();
}
~~~

**Hỏi:** Thiếu thao tác nào?

**Đáp án:** Nếu context chưa joined, cần `em.joinTransaction()` sau khi transaction active, trước khi muốn flush. Có thể đặt join trước `persist` để làm rõ luồng ghi.

### Bài 3. Gọi join mà không có transaction

~~~java
@TransactionAttribute(TransactionAttributeType.NOT_SUPPORTED)
public void preview() {
    em.joinTransaction();
}
~~~

**Hỏi:** Vì sao có thể bị lỗi?

**Đáp án:** `NOT_SUPPORTED` không thực thi method trong JTA transaction; `joinTransaction` không có transaction để tham gia. Không gọi join ở đây; mở transaction ở bước thực sự cần ghi.

### Bài 4. Kiểm tra trạng thái

~~~java
if (!em.isJoinedToTransaction()) {
    em.joinTransaction();
}
~~~

**Hỏi:** Có phải đây là logic luôn an toàn không?

**Đáp án:** Chưa đủ. `isJoinedToTransaction() == false` có thể do **không có transaction active**. Phải biết transaction manager thực sự đã mở giao dịch thích hợp trước khi join.

### Bài 5. Gọi flush nhưng chưa join

Một unsynchronized context giữ đơn hàng nháp, service vào transaction và gọi `em.flush()` mà không join.

**Đáp án:** Flush không thay thế join. Cần explicit `joinTransaction()` khi transaction active, rồi mới flush nếu muốn đồng bộ pending changes.

### Bài 6. Một entity detached trước khi join

Một entity được tải trong EM cũ đã đóng. Service tạo EM mới, gọi `joinTransaction()`, rồi sửa trực tiếp object detached.

**Đáp án:** Join chỉ tác động đến context mới. Muốn thay đổi được theo dõi, cần nạp lại managed entity hoặc `merge` theo ngữ nghĩa JPA, không giả định object detached được tự attach.

### Bài 7. Dữ liệu sau rollback

Sau khi `joinTransaction` và `flush` thành công, business method ném exception khiến JTA rollback.

**Đáp án:** Những thay đổi SQL chưa commit bị rollback. `joinTransaction` và `flush` không có vai trò commit, nên không thể xem flush thành công là xác nhận lưu bền vững.

### Bài 8. App-managed EM tạo trước transaction

`EntityManager` được tạo từ `EntityManagerFactory` trước khi transaction bắt đầu. Sau đó service vào một JTA transaction active và muốn ghi bằng EM này.

**Đáp án:** Cần kiểm tra việc EM đã tham gia transaction hay chưa. Nếu chưa, `joinTransaction()` là API JPA để yêu cầu gia nhập; dùng EM đúng phạm vi, không chia sẻ nhiều thread, và đóng application-managed EM khi xong.

### Bài 9. Spring @Transactional có đồng nghĩa JTA?

**Đáp án:** Không. Spring có thể dùng nhiều transaction manager. `joinTransaction()` là vấn đề của **JTA entity manager**, không phải một lời gọi bắt buộc chỉ vì method có `@Transactional`.

### Bài 10. Hai persistence units

Service đang dùng hai EM thuộc hai JTA persistence units, gọi `joinTransaction()` trên cả hai rồi cho rằng giao dịch đa DB sẽ luôn atomic.

**Đáp án:** Không đủ. Khả năng phối hợp nhiều resource phụ thuộc transaction manager, driver, datasource và cấu hình JTA/XA. `joinTransaction()` chỉ yêu cầu tham gia transaction đang có.

## 20. Khuyến nghị thiết kế

### 20.1. Trường hợp nên để container/framework tự quản lý

Phần lớn service CRUD có thể sử dụng:

~~~java
@Transactional
public void create(String code) {
    em.persist(new PurchaseOrder(code));
}
~~~

với transaction manager và injected entity manager phù hợp. Nếu context synchronized và được tích hợp đúng, không nên thêm `joinTransaction()` chỉ để “bảo đảm đã lưu”.

### 20.2. Trường hợp nên cân nhắc explicit join

- `@PersistenceContext(synchronization = UNSYNCHRONIZED)`: muốn context tham gia transaction tại một bước cụ thể.
- Extended unsynchronized persistence context: giữ state qua các bước rồi chỉ join khi quyết định lưu.
- JTA application-managed `EntityManager`: được tạo trước transaction, sau đó cần sử dụng trong JTA transaction active.
- Một quy trình đặc biệt có nhiều persistence contexts và transaction boundaries rõ ràng, cần kiểm soát tham gia giao dịch theo hợp đồng provider/JPA.

### 20.3. Trường hợp không nên dùng joinTransaction như giải pháp

- Cần mở transaction mới: dùng transaction manager, không phải join.
- Cần commit: dùng JTA manager/container, không phải join.
- Cần đồng bộ SQL: dùng flush **sau khi đã tham gia transaction hợp lệ**.
- Cần attach detached entity: dùng find/merge thích hợp.
- Cần load lazy associations: dùng fetch join, entity graph hoặc query phù hợp.
- Cần giải quyết lỗi khóa ngoại: sửa object graph/mapping hoặc trình tự nghiệp vụ.
- Đang dùng RESOURCE_LOCAL: dùng `EntityTransaction`, không lấy joinTransaction làm thay thế.

## 21. Kết luận

Có thể hiểu chính xác `joinTransaction()` theo một câu:

> **`EntityManager.joinTransaction()` yêu cầu một JTA persistence context tham gia JTA transaction đang hoạt động; nó không bắt đầu transaction và không commit dữ liệu.**

Khi dùng **synchronized container-managed context** trong service giao dịch thông thường, container/provider thường đảm nhận việc tham gia tự động. Khi dùng **unsynchronized context** hoặc **application-managed JTA entity manager tạo ngoài transaction**, explicit join có thể là bước thiết yếu để các thay đổi đang chờ được đồng bộ đúng giao dịch.

Luôn tách rõ ba trách nhiệm: **transaction manager mở và kết thúc JTA transaction; entity manager duy trì persistence context; `joinTransaction` kết nối chúng khi cần**. Sau đó mới dùng `persist`, dirty checking và `flush` để đồng bộ dữ liệu, và chỉ xem quá trình lưu hoàn tất khi transaction được commit thành công.

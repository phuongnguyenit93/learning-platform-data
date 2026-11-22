# Ngữ cảnh đồng bộ và không đồng bộ với giao dịch JTA trong JPA

## 1. Vì sao cần phân biệt synchronized và unsynchronized?

Trong Jakarta Persistence (JPA), một **persistence context** quản lý các entity theo danh tính, trạng thái và vòng đời. JPA provider dùng persistence context để theo dõi những entity đã tải, những entity mới được persist và những thay đổi đang chờ ghi xuống database.

Khi ứng dụng dùng **Jakarta Transactions (JTA)**, transaction có thể do container hoặc transaction manager quản lý. Một câu hỏi quan trọng xuất hiện: **persistence context có tự tham gia transaction JTA đang hoạt động không, hay ứng dụng phải yêu cầu tham gia?**

JPA cung cấp hai kiểu đồng bộ với JTA:

- **SynchronizationType.SYNCHRONIZED:** persistence context được quản lý theo mô hình tự tham gia transaction JTA phù hợp. Khi đã tham gia, các thay đổi có thể được flush trong transaction và phải được đồng bộ theo quy tắc transaction trước khi commit thành công.
- **SynchronizationType.UNSYNCHRONIZED:** persistence context **không tự động tham gia** transaction JTA chỉ vì có transaction đang hoạt động. Ứng dụng chủ động gọi **EntityManager.joinTransaction()** khi muốn context tham gia một transaction cụ thể.

Khác biệt này đặc biệt hữu ích trong luồng **soạn nháp nhiều bước**: người dùng có thể chỉnh một tập entity trong một persistence context sống lâu hơn một transaction, rồi chỉ khi bấm “Lưu” mới đưa những thay đổi đó vào một transaction JTA để commit.

Hãy hình dung:

~~~text
          Persistence context
         /                   \
        v                     v
  SYNCHRONIZED          UNSYNCHRONIZED
  Tự tham gia JTA       Không tự tham gia JTA
  khi điều kiện         dù có JTA đang chạy
  phù hợp
        |                     |
        v                     | em.joinTransaction()
  Flush trong JTA             v
        |                 Tham gia JTA
        |                     |
        +----------+----------+
                   v
           Flush và DB commit
           theo transaction
~~~

**“Đồng bộ” ở đây nghĩa là đồng bộ persistence context với giao dịch JTA, không phải đồng bộ đa luồng Java, đồng bộ dữ liệu giữa microservice, hay lựa chọn khi nào chạy một câu SELECT.**

## 2. Các khái niệm cần nắm trước

### 2.1. Persistence context và EntityManager

**EntityManager** là API để thao tác với persistence context: tìm entity, persist, merge, remove, flush và query. Một context có thể chứa:

- Entity đã tải từ database, đang ở trạng thái **managed**.
- Entity mới được đưa vào context bằng **persist()**.
- Các thay đổi thuộc tính do dirty checking theo dõi.
- Các thay đổi liên kết collection, cascade, orphan removal và version.

JPA quản lý danh tính entity trong một persistence context: một entity type với cùng primary key thường tương ứng một managed instance. Nhưng **entity đang managed không đồng nghĩa các thay đổi của nó đã được commit**.

### 2.2. JTA transaction

JTA cung cấp cơ chế transaction được quản lý bên ngoài một EntityManager cụ thể. Tùy nền tảng, ứng dụng có thể dùng container-managed transaction (CMT), **jakarta.transaction.Transactional**, hoặc **UserTransaction** trong những môi trường được phép điều khiển transaction thủ công.

Một JTA transaction có thể phối hợp nhiều resource đủ điều kiện tham gia, tùy transaction manager, datasource và khả năng XA hoặc cơ chế transaction được cấu hình. **joinTransaction() chỉ yêu cầu persistence context tham gia JTA hiện tại; nó không tự biến mọi resource bên ngoài thành resource có thể rollback cùng transaction.**

### 2.3. Flush và commit

**Flush** đồng bộ trạng thái persistence context tới database bằng SQL khi cần; **commit** xác nhận transaction. SQL có thể chạy trước commit, và rollback có thể hoàn tác DML chưa commit.

~~~text
persist()/sửa managed entity
             |
             v
     Thay đổi trong context
             |
             v
   Context đã tham gia JTA?
       /             \
     chưa             rồi
      |                |
 Không flush           v
 vào JTA này       flush khi cần
      |                |
  joinTransaction()     |
      |                |
      +--------->------+----> JTA commit hoặc rollback
~~~

Trong unsynchronized context, **có transaction JTA đang chạy chưa đủ** để các thay đổi được tự động flush vào transaction đó.

### 2.4. Những trục cấu hình độc lập

Ba lựa chọn khác nhau dễ bị nhầm:

| Trục | Các giá trị thường gặp | Câu hỏi được giải quyết |
|---|---|---|
| **Transaction type** của persistence unit | JTA, RESOURCE_LOCAL | Ai quản lý transaction của EntityManager? |
| **Persistence context type** | TRANSACTION, EXTENDED | Context sống trong phạm vi nào? |
| **Synchronization type** | SYNCHRONIZED, UNSYNCHRONIZED | Context có tự tham gia JTA hay cần join thủ công? |
| **Flush mode** | AUTO, COMMIT | Khi đã tham gia transaction, provider cân nhắc flush trước query như thế nào? |

Đặc biệt, **SynchronizationType.UNSYNCHRONIZED không phải FlushModeType.COMMIT**. Hai cấu hình có mục đích và phạm vi khác nhau.

## 3. Khai báo một persistence unit JTA

Trong Jakarta EE, persistence unit dùng JTA có thể khai báo trong **META-INF/persistence.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence
        https://jakarta.ee/xml/ns/persistence/persistence_3_1.xsd"
    version="3.1">

    <persistence-unit name="catalogPu"
                      transaction-type="JTA">
        <jta-data-source>java:comp/DefaultDataSource</jta-data-source>

        <class>com.example.catalog.Product</class>

        <properties>
            <property name="jakarta.persistence.schema-generation.database.action"
                      value="none"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

**Tên JNDI của datasource là ví dụ**, cần dùng đúng datasource do server cung cấp. Dùng **jta-data-source** cho transaction JTA theo cách platform/provider hỗ trợ. Việc tạo bảng bằng migration được giả định thực hiện ngoài ví dụ; cấu hình **database.action=none** không tự tạo schema.

Một entity minh họa:

~~~java
package com.example.catalog;

import jakarta.persistence.*;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "product_id_generator"
    )
    @SequenceGenerator(
        name = "product_id_generator",
        sequenceName = "product_id_seq",
        allocationSize = 1
    )
    private Long id;

    @Column(name = "code", nullable = false, unique = true, length = 40)
    private String code;

    @Column(name = "display_name", nullable = false, length = 150)
    private String displayName;

    @Version
    private long version;

    protected Product() {}

    public Product(String code, String displayName) {
        this.code = code;
        this.displayName = displayName;
    }

    public Long getId() { return id; }
    public String getCode() { return code; }
    public String getDisplayName() { return displayName; }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("display name required");
        }
        this.displayName = newName;
    }
}
~~~

Ví dụ dùng sequence để dễ minh họa việc entity được đưa vào context trước khi INSERT. Khi chạy trên MySQL hoặc DB khác, cần chọn strategy/generator phù hợp; **sự khác nhau về IDENTITY và SEQUENCE không thay đổi nguyên tắc tham gia JTA**.

## 4. SYNCHRONIZED: persistence context tham gia JTA như thế nào?

Đây là lựa chọn mặc định của một container-managed EntityManager được inject qua **@PersistenceContext** nếu không chỉ rõ synchronization:

~~~java
import jakarta.ejb.Stateless;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

@Stateless
public class ProductService {

    @PersistenceContext(unitName = "catalogPu")
    private EntityManager em;

    public Long create(String code, String name) {
        Product product = new Product(code, name);
        em.persist(product);
        return product.getId();
    }
}
~~~

Trong ví dụ này, **@Stateless** là Jakarta Enterprise Beans (EJB). Với container-managed transaction mặc định của stateless session bean, một business method thường chạy theo transaction attribute **REQUIRED**. Container cung cấp một JTA transaction khi cần, và synchronized persistence context tham gia transaction phù hợp.

**Không cần gọi joinTransaction() tường minh trong luồng chuẩn này.** Provider có thể flush khi query đòi hỏi, khi ứng dụng gọi em.flush() hoặc khi transaction chuẩn bị commit.

### 4.1. Khai báo tường minh synchronized

~~~java
@PersistenceContext(
    unitName = "catalogPu",
    synchronization = SynchronizationType.SYNCHRONIZED
)
private EntityManager em;
~~~

Lựa chọn này có cùng ý định đồng bộ JTA mặc định. Import:

~~~java
import jakarta.persistence.SynchronizationType;
~~~

### 4.2. Timeline điển hình

~~~text
Container bắt đầu JTA transaction T1
         |
         v
Synchronized EntityManager sử dụng persistence context
         |
         v
em.persist(new Product(...))
         |
         v
Provider có thể lấy ID từ sequence
         |
         v
em.flush() hoặc auto flush khi query cần
         |
         v
SQL INSERT được thực thi trong T1
         |
         v
Container commit T1
~~~

SQL có thể được thực thi trước commit, nhưng dữ liệu chưa commit vẫn chịu isolation của database. **EntityManager.persist() không tự tạo một transaction mới** và **cũng không phải lệnh commit**.

### 4.3. Synchronized không đồng nghĩa “luôn flush ngay”

~~~java
Product p = em.find(Product.class, 10L);
p.rename("Laptop văn phòng");
~~~

Với entity managed, provider có thể để trạng thái dirty trong context cho tới thời điểm flush thích hợp. Cái được tự động hóa bởi **SYNCHRONIZED** là **việc tham gia transaction**, không phải việc mỗi setter đều lập tức phát UPDATE.

## 5. UNSYNCHRONIZED: giữ thay đổi ngoài việc tham gia JTA tự động

Với **SynchronizationType.UNSYNCHRONIZED**, persistence context có thể được dùng để quản lý trạng thái mà **không tự động được enlisted vào JTA transaction hiện tại**.

Ví dụ khai báo:

~~~java
@PersistenceContext(
    unitName = "catalogPu",
    synchronization = SynchronizationType.UNSYNCHRONIZED
)
private EntityManager em;
~~~

Lúc đó, **một method đang có JTA transaction không đồng nghĩa context này đã tham gia transaction**. Ứng dụng có thể gọi **em.joinTransaction()** để yêu cầu tham gia.

### 5.1. Vì sao cần unsynchronized?

Một số màn hình là quá trình chỉnh sửa nhiều bước:

~~~text
Người dùng mở mẫu tạo đơn hàng
       |
       v
Thêm 3 dòng hàng (chưa nhấn Lưu)
       |
       v
Sửa số lượng, nhập ghi chú
       |
       v
Xem lại nội dung nháp
       |
       v
Nhấn "Lưu đơn hàng"
       |
       v
joinTransaction() và commit JTA
~~~

Nếu persistence context sống xuyên nhiều bước, unsynchronized giúp trì hoãn việc đưa những thay đổi vào một transaction JTA cụ thể cho đến lúc ứng dụng chủ động quyết định.

**Điều kiện quan trọng:** persistence context phải **còn sống** tới lúc commit dự kiến. Unsynchronized **không tự kéo dài vòng đời** của transaction-scoped persistence context; cần thiết kế scope và lifecycle phù hợp, thường xem xét **extended persistence context** cho cuộc hội thoại nhiều bước.

### 5.2. Những gì UNSYNCHRONIZED không có nghĩa

| Nhận định | Đúng hay sai? |
|---|---|
| Không tự join JTA chỉ vì JTA đang hoạt động | **Đúng** |
| Có thể chủ động join JTA bằng em.joinTransaction() | **Đúng** |
| Bất kỳ lúc nào cũng có thể flush dù chưa join | **Sai** |
| Có JTA transaction thì các thay đổi unjoined sẽ tự commit | **Sai** |
| Các managed entity mất hết trạng thái ngay khi không join | **Sai**, tùy vòng đời context |
| Unsynchronized tự tạo một transaction ngầm để INSERT | **Sai** |
| Unsynchronized đồng nghĩa FlushModeType.COMMIT | **Sai** |
| Unsynchronized làm EntityManager thread-safe | **Sai** |
| Unsynchronized là giải pháp tự động cho mọi bài toán draft | **Sai**, còn lifecycle, isolation và dữ liệu cũ |

### 5.3. Query trước khi join

Một unsynchronized persistence context vẫn có thể hỗ trợ các thao tác đọc và quản lý trạng thái theo điều kiện JPA/runtime. Nhưng **pending changes chưa được flush** không mặc nhiên xuất hiện trong kết quả một JPQL query dựa trên database.

Ví dụ:

~~~java
em.persist(new Product("PRD-100", "Sản phẩm nháp"));

// Không giả định count() sau đây chắc đã tính cả entity mới
// nếu persistence context chưa join JTA và chưa flush.
Long count = em.createQuery(
    "select count(p) from Product p where p.code = :code",
    Long.class
).setParameter("code", "PRD-100")
 .getSingleResult();
~~~

Một entity được quản lý trong context có thể được lấy lại bằng identity lookup từ context, trong khi một query count() vẫn chạy dựa trên DB, nơi pending INSERT chưa tồn tại. Vì vậy **không dùng query trước join để xác nhận đã “lưu xong”**.

Nếu cần validation trước khi commit, có thể kiểm tra object trong bộ nhớ theo quy tắc domain, hoặc join vào transaction rồi flush để DB kiểm tra constraint. Những truy vấn kiểm tra “chưa có mã trùng” không thay thế UNIQUE constraint thực trong DB.

## 6. joinTransaction() và isJoinedToTransaction()

Hai API trung tâm của chủ đề:

~~~java
em.joinTransaction();
boolean joined = em.isJoinedToTransaction();
~~~

**joinTransaction()** yêu cầu persistence context tham gia **JTA transaction hiện tại**. **isJoinedToTransaction()** cho biết context có đang tham gia transaction hiện tại hay không.

### 6.1. Ví dụ trong một transaction đang hoạt động

~~~java
@PersistenceContext(
    unitName = "catalogPu",
    synchronization = SynchronizationType.UNSYNCHRONIZED
)
private EntityManager em;

public void createInsideJta(String code, String name) {
    Product product = new Product(code, name);
    em.persist(product);

    boolean before = em.isJoinedToTransaction(); // false khi chưa join

    em.joinTransaction();

    boolean after = em.isJoinedToTransaction();  // true khi join thành công
    em.flush();
}
~~~

**Ví dụ chỉ đúng khi method thực sự chạy trong JTA transaction đang hoạt động**, chẳng hạn do container-managed transaction hoặc @Transactional phù hợp. Nếu gọi ngoài JTA, joinTransaction() không phải lệnh tự mở transaction.

### 6.2. Trước và sau join có gì khác?

| Trạng thái | Chưa join JTA | Sau khi join JTA |
|---|---|---|
| Entity được quản lý trong context | Có thể có | Có thể có |
| Dirty state tồn tại trong context | Có thể có | Có thể có |
| Provider tự flush vào JTA này | Không tự động chỉ vì JTA đang chạy | Có thể flush khi cần |
| em.flush() yêu cầu đồng bộ vào transaction | Không hợp lệ nếu chưa join transaction phù hợp | Hợp lệ trong transaction phù hợp |
| JTA commit xử lý pending changes của context | Không tự cam kết context chưa join | Phải xem xét đồng bộ theo contract |
| SQL có tham gia transaction hiện tại | Không được suy ra chỉ từ việc JTA tồn tại | Được phối hợp khi context đã join |

### 6.3. Khi nào joinTransaction() không phù hợp?

- Không có transaction JTA đang hoạt động để tham gia.
- Persistence unit thực tế là **RESOURCE_LOCAL**, không phải JTA.
- EntityManager đã đóng hoặc context không còn trong trạng thái hợp lệ.
- Framework/container đang dùng một persistence context khác có phạm vi hoặc synchronization xung đột.

Trong những tình huống không hợp lệ, provider có thể ném exception như **TransactionRequiredException** hoặc **IllegalStateException** tùy nguyên nhân và API. Không dùng joinTransaction() như biện pháp sửa chung cho bất kỳ lỗi persistence nào.

### 6.4. Join không đồng nghĩa flush hoặc commit

~~~java
em.joinTransaction(); // Bắt đầu tham gia JTA hiện tại.
em.flush();           // Yêu cầu đồng bộ nếu cần.
// JTA transaction chưa commit chỉ vì hai lời gọi trên.
~~~

joinTransaction() thiết lập quan hệ tham gia transaction; flush mới yêu cầu đồng bộ trạng thái, còn commit do transaction manager thực hiện. Một số SQL cấp ID có thể xảy ra sớm theo provider, nhưng đó không thay đổi ý nghĩa API.

### 6.5. Một context có thể tham gia nhiều transaction ở các thời điểm khác nhau?

Với **extended persistence context**, cùng một context có thể sống qua nhiều transaction ở các thời điểm khác nhau. Sau khi transaction đã kết thúc, context có thể tiếp tục tồn tại và quản lý entity cho cuộc hội thoại. Nếu dùng kiểu **UNSYNCHRONIZED**, ứng dụng cần xác định rõ khi nào nó được join vào **transaction tiếp theo**; không nên mặc định đã join một transaction trước thì mọi transaction tương lai đều tự động có những thay đổi cần commit.

Một persistence context cũng không nên bị dùng đồng thời từ nhiều thread hoặc trong hai transaction cạnh tranh để sửa cùng managed entity. EntityManager **không được thiết kế như một object thread-safe dùng chung**.

## 7. Transaction-scoped và extended: không phải synonyms của synchronized và unsynchronized

**PersistenceContextType.TRANSACTION** thường có vòng đời gắn với transaction. **PersistenceContextType.EXTENDED** sống xuyên nhiều transaction theo lifecycle của component/container phù hợp. Hai lựa chọn này độc lập về khái niệm với SYNCHRONIZED/UNSYNCHRONIZED.

| Scope | SYNCHRONIZED | UNSYNCHRONIZED |
|---|---|---|
| **TRANSACTION** | Mô hình thông thường của dịch vụ request/transaction; tự tham gia JTA phù hợp | Không auto join; cần xác định rõ lifecycle, không nên nhầm với lưu nháp lâu dài |
| **EXTENDED** | Context sống lâu, có thể tham gia JTA phù hợp theo cơ chế container | Context sống lâu và có thể giữ thay đổi chưa tham gia JTA; ứng dụng chủ động join khi lưu |

### 7.1. Transaction-scoped context

~~~java
@PersistenceContext(
    unitName = "catalogPu",
    type = PersistenceContextType.TRANSACTION
)
private EntityManager em;
~~~

Đây là lựa chọn mặc định thông dụng trong service giao dịch. Với CMT và synchronized, EntityManager được container cung cấp tham gia transaction khi cần. Sau khi transaction kết thúc, context transaction-scoped không tiếp tục đóng vai trò một bộ nhớ nháp dài hạn qua nhiều request độc lập.

**Không nên mong pending entities của một transaction-scoped unsynchronized context sẽ tồn tại vô hạn** chỉ nhờ thêm UNSYNCHRONIZED. Nếu cần giữ trạng thái trong một quá trình nhiều bước, phải có scope mở rộng đúng nghĩa hoặc cách lưu nháp riêng.

### 7.2. Extended context

Trong Jakarta Enterprise Beans, extended persistence context thường được gắn với **stateful session bean**:

~~~java
@Stateful
public class DraftEditor {

    @PersistenceContext(
        unitName = "catalogPu",
        type = PersistenceContextType.EXTENDED,
        synchronization = SynchronizationType.UNSYNCHRONIZED
    )
    private EntityManager em;
}
~~~

Lớp này chỉ minh họa injection; ví dụ hoàn chỉnh hơn nằm ở phần kế tiếp.

Extended context thích hợp khi:

- Một cuộc hội thoại người dùng trải qua nhiều lời gọi.
- Cần giữ identity và thay đổi object giữa các bước.
- Có ranh giới transaction commit rõ.

Nhưng chi phí đi kèm:

- Giữ managed objects lâu làm tăng memory pressure.
- State trong context có thể cũ so với database vì các transaction khác vẫn ghi.
- Optimistic locking có thể phát hiện xung đột lúc join/flush/commit, không phải lúc người dùng sửa form.
- Cần quản lý lifecycle khi người dùng hủy nháp, timeout, component bị hủy hoặc failover.

### 7.3. Extended synchronized có giống extended unsynchronized không?

**Không.** Extended nói về **thời gian sống của context**. Synchronized nói về **tham gia transaction**. Một extended synchronized context vẫn có thể tự tham gia các JTA transaction phù hợp, khiến những thay đổi tích lũy được đồng bộ tại một transaction mà người thiết kế chưa định dùng để “Lưu nháp”.

Nếu yêu cầu là **giữ thay đổi chưa commit qua nhiều lượt thao tác** và chỉ join ở nút Submit, extended **unsynchronized** thể hiện rõ hơn mục đích đó. Tuy nhiên, việc giữ state lâu phải có kế hoạch quản lý concurrency và stale data.

## 8. Ví dụ hoàn chỉnh: biên tập nháp bằng stateful session bean

Ví dụ dưới đây giả định ứng dụng Jakarta EE với JTA persistence unit **catalogPu**. Một editor gắn với một phiên làm việc nghiệp vụ dùng extended unsynchronized context. EJB container quản lý transaction cho từng business method.

~~~java
package com.example.catalog;

import jakarta.ejb.Stateful;
import jakarta.ejb.Remove;
import jakarta.ejb.TransactionAttribute;
import jakarta.ejb.TransactionAttributeType;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.PersistenceContextType;
import jakarta.persistence.SynchronizationType;

@Stateful
public class ProductDraftEditor {

    @PersistenceContext(
        unitName = "catalogPu",
        type = PersistenceContextType.EXTENDED,
        synchronization = SynchronizationType.UNSYNCHRONIZED
    )
    private EntityManager em;

    private Product draft;

    @TransactionAttribute(TransactionAttributeType.NOT_SUPPORTED)
    public void startDraft(String code, String name) {
        if (draft != null) {
            throw new IllegalStateException("Draft already active");
        }
        draft = new Product(code, name);
        em.persist(draft);
        // Context giữ thay đổi; không mở transaction JTA để commit.
    }

    @TransactionAttribute(TransactionAttributeType.NOT_SUPPORTED)
    public void renameDraft(String name) {
        if (draft == null) {
            throw new IllegalStateException("No draft");
        }
        draft.rename(name);
        // Chỉ đổi trạng thái managed object trong context.
    }

    @TransactionAttribute(TransactionAttributeType.REQUIRED)
    public Long submitDraft() {
        if (draft == null) {
            throw new IllegalStateException("No draft");
        }

        em.joinTransaction();
        em.flush();

        Long id = draft.getId();
        // Container commit JTA transaction nếu method hoàn tất.
        draft = null;
        return id;
    }

    @Remove
    @TransactionAttribute(TransactionAttributeType.NOT_SUPPORTED)
    public void discardEditor() {
        // Container kết thúc bean/context theo lifecycle đã cấu hình.
        // Không join JTA chỉ để hủy nháp.
    }
}
~~~

### 8.1. Luồng hoạt động

~~~text
ProductDraftEditor được tạo
          |
          v
startDraft()
  em.persist(Product)
  context chưa join JTA
          |
          v
renameDraft()
  sửa managed Product
  vẫn chưa join JTA
          |
          v
submitDraft()
  container mở/tham gia JTA T1
  em.joinTransaction()
  em.flush()
  container commit T1
          |
          v
Product tồn tại dưới ID đã commit
~~~

Với mapping SEQUENCE, provider có thể cần cấp ID vào một thời điểm hợp lệ; **không được dựa vào ID xuất hiện trước join/commit** để suy ra dữ liệu đã tồn tại trong DB. Với một chiến lược ID khác như IDENTITY, thời điểm cấp ID còn phụ thuộc provider.

### 8.2. Trách nhiệm chưa giải quyết trong ví dụ

Ví dụ tập trung minh họa synchronization, **không phải toàn bộ thiết kế session người dùng**. Ứng dụng thực cần:

- Bảo đảm một client nhận đúng stateful bean instance của mình.
- Quy định thời điểm hủy bean, timeout, passivation và tài nguyên của extended context.
- Kiểm tra quyền ghi, duplicate code, các field bắt buộc và validation.
- Xử lý exception tại flush/commit theo policy container; sau lỗi giao dịch có thể phải bỏ nháp và tạo context mới.
- Kiểm soát việc client sửa nháp trong lúc dữ liệu cùng loại được transaction khác sửa.
- Không chia sẻ một EntityManager hoặc stateful editor không an toàn giữa nhiều thread.

**Quan trọng:** Với cơ chế container-managed transaction, ứng dụng không gọi **em.getTransaction().commit()** trong EJB này. JTA commit do container quyết định sau method.

## 9. Ví dụ application-managed JTA EntityManager

Ngoài injection qua @PersistenceContext, ứng dụng có thể tạo EntityManager từ **EntityManagerFactory**:

~~~java
EntityManager em =
    emf.createEntityManager(SynchronizationType.UNSYNCHRONIZED);
~~~

Phương thức này chọn unsynchronized context cho một **JTA entity manager**. Nó không nên được dùng như phương án thay thế tương đương cho một RESOURCE_LOCAL entity manager.

### 9.1. Tạo một transaction bằng UserTransaction

Trong môi trường Jakarta EE **cho phép ứng dụng điều khiển UserTransaction** (không phải EJB CMT), có thể minh họa:

~~~java
package com.example.catalog;

import jakarta.annotation.Resource;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.PersistenceUnit;
import jakarta.persistence.SynchronizationType;
import jakarta.transaction.UserTransaction;

public class JtaWriteExample {

    @PersistenceUnit(unitName = "catalogPu")
    private EntityManagerFactory emf;

    @Resource
    private UserTransaction utx;

    public Long createProduct(String code, String name) throws Exception {
        EntityManager em = emf.createEntityManager(
            SynchronizationType.UNSYNCHRONIZED
        );

        boolean transactionStarted = false;
        try {
            utx.begin();
            transactionStarted = true;

            Product product = new Product(code, name);
            em.persist(product);

            // Tại đây context chưa auto join JTA.
            boolean joinedBefore = em.isJoinedToTransaction();

            em.joinTransaction();
            boolean joinedAfter = em.isJoinedToTransaction();
            if (!joinedAfter) {
                throw new IllegalStateException("Context did not join JTA");
            }

            em.flush();
            Long id = product.getId();

            utx.commit();
            transactionStarted = false;
            return id;
        } catch (Exception ex) {
            if (transactionStarted) {
                try {
                    utx.rollback();
                } catch (Exception rollbackFailure) {
                    ex.addSuppressed(rollbackFailure);
                }
            }
            throw ex;
        } finally {
            em.close();
        }
    }
}
~~~

Ví dụ giả định container cung cấp **@PersistenceUnit** và **@Resource UserTransaction** hợp lệ cho loại component đang chạy. Không copy nguyên vào một EJB dùng **container-managed transactions**, nơi quyền gọi UserTransaction có giới hạn khác. Trong production, nên để transaction manager và framework hiện có điều phối transaction thay vì tự viết lại logic này nếu không cần thiết.

### 9.2. Điểm cần quan sát

1. EntityManager được tạo với **UNSYNCHRONIZED**.
2. **utx.begin()** mở JTA transaction nhưng không tự join persistence context.
3. **em.isJoinedToTransaction()** giúp quan sát việc tham gia.
4. **em.joinTransaction()** yêu cầu context tham gia transaction.
5. **em.flush()** đồng bộ những thay đổi cần thiết trong JTA.
6. **utx.commit()** là bước xác nhận transaction.
7. **em.close()** giải phóng application-managed EntityManager sau khi dùng.

Trong môi trường sử dụng CMT hoặc Spring @Transactional, nên để framework quản lý các bước begin/commit/rollback, và chỉ dùng **joinTransaction()** khi thực sự cần điều khiển việc tham gia của unsynchronized context.

## 10. Unsynchronized nhưng có JTA đang chạy: điều gì xảy ra?

Đây là điểm dễ gây lỗi nhất. Giả sử một phương thức JTA làm:

~~~java
@Transactional
public void attemptWrite() {
    Product p = new Product("P-01", "Bản nháp");
    em.persist(p);

    // em là UNSYNCHRONIZED và chưa joinTransaction().
    // Không được suy ra JTA commit sẽ tự flush p.
}
~~~

Nếu persistence context chưa join transaction, **JTA commit không có nghĩa provider đã tự động đồng bộ các thay đổi trong context đó**. Một số dữ liệu chỉ tồn tại trong bộ nhớ của context và có thể không được lưu. Nếu context là extended, trạng thái có thể còn sau method; nếu context có lifecycle ngắn, state có thể bị mất khi context kết thúc.

### 10.1. Vì sao commit không tự lôi mọi context vào?

Một ứng dụng có thể có nhiều EntityManager và nhiều context. Không phải mọi context tồn tại cùng lúc với một transaction đều được phép tự gắn vào transaction đó; nếu không, một thao tác giao dịch không liên quan có thể vô tình commit dữ liệu nháp.

Đó chính là lý do tồn tại UNSYNCHRONIZED: **quyền quyết định tham gia transaction nằm ở ứng dụng**.

### 10.2. Flush trước join có hợp lệ không?

~~~java
@Transactional
public void flushTooEarly() {
    em.persist(new Product("P-02", "Chưa join"));
    em.flush();  // Không hợp lệ nếu context chưa tham gia JTA.
}
~~~

Một unsynchronized persistence context **chưa join vào transaction phù hợp không được flush trạng thái của nó vào transaction đó**. API flush trong điều kiện không có transaction hợp lệ/không tham gia thường dẫn tới **TransactionRequiredException**.

Điều này khác việc em.persist() cập nhật bộ nhớ context: tùy scope và điều kiện của JPA, một extended unsynchronized context có thể giữ pending changes chưa flush, nhưng **flush muốn ghi DB phải có transaction tham gia**.

### 10.3. Đừng coi exception là cách xác định chiến lược

Không cần chờ em.flush() ném exception mới biết context chưa join. Trong code có ranh giới rõ, hãy gọi **em.isJoinedToTransaction()** khi có JTA active, và chủ động **joinTransaction()** tại điểm đã định.

Nếu một transaction đã bị đánh dấu rollback-only do lỗi flush/constraint, không nên bắt exception rồi tiếp tục dùng context như thể tất cả thay đổi đã được hủy sạch. Thường cần rollback và làm mới scope/context thích hợp.

## 11. FlushModeType.AUTO/COMMIT khác synchronization

Hai khái niệm dễ bị đặt cùng một hàng vì đều có chữ “đồng bộ”.

**SynchronizationType** trả lời: *Context có tham gia transaction JTA này không?*

**FlushModeType** trả lời: *Khi context có thể đồng bộ và có query trong transaction, provider cần cân nhắc flush theo cơ chế nào?*

| Tình huống | SYNCHRONIZED | UNSYNCHRONIZED chưa join |
|---|---|---|
| FlushModeType.AUTO | Provider bảo đảm query phản ánh những pending changes liên quan theo contract JPA khi tham gia transaction | Không tạo quyền flush vào JTA chỉ vì AUTO |
| FlushModeType.COMMIT | Đồng bộ theo contract COMMIT; hiệu ứng pending changes lên query trước commit không được đặc tả đầy đủ | Không khiến context tự tham gia JTA |
| em.flush() | Hợp lệ khi có transaction đã tham gia | Chưa hợp lệ nếu chưa join JTA phù hợp |
| JTA commit | Đồng bộ những thay đổi cần thiết của context tham gia | Không tự cam kết pending changes của context chưa join |

Ví dụ:

~~~java
em.setFlushMode(FlushModeType.AUTO);
// Không tự động biến UNSYNCHRONIZED thành SYNCHRONIZED.

em.joinTransaction();
// Context bắt đầu tham gia JTA hiện tại.

em.flush();
// Có thể thực thi INSERT/UPDATE/DELETE trong JTA.
~~~

**FlushModeType.COMMIT cũng không có nghĩa mọi SQL bị cấm trước commit**: một query vẫn có thể SELECT, một generator có thể cần SQL và một flush tường minh vẫn có thể thực thi khi context đã join.

## 12. Cơ chế đồng bộ thực sự: timeline hai phiên bản

### 12.1. SYNCHRONIZED mặc định

~~~text
T1 BEGIN
   |
   +-- Container cung cấp synchronized EM
   |
   +-- find(Product #10)
   |
   +-- product.rename("Tên mới")
   |
   +-- JPQL query có thể yêu cầu AUTO flush
   |       |
   |       +-- SQL UPDATE có thể thực thi trong T1
   |
   +-- T1 COMMIT
           |
           +-- flush phần còn chờ nếu cần
           +-- xác nhận transaction
~~~

### 12.2. UNSYNCHRONIZED với explicit join

~~~text
Extended unsynchronized context được tạo
   |
   +-- persist(Product A)      [pending]
   |
   +-- rename(Product A)       [pending]
   |
T1 BEGIN
   |
   +-- component thực hiện bước nghiệp vụ khác
   |
   +-- context chưa tham gia T1
   |       |
   |       +-- pending Product A chưa tự flush vào T1
   |
   +-- em.joinTransaction()
   |
   +-- em.flush()
   |       |
   |       +-- SQL INSERT/UPDATE thuộc T1
   |
   +-- T1 COMMIT
           |
           +-- những DML của context đã join được xác nhận
~~~

Điểm khác biệt nằm ở **trước khi joinTransaction()**. Sau khi đã tham gia một transaction, unsynchronized context có thể được đồng bộ theo những quy tắc flush/transaction phù hợp như một context đã tham gia. Nhưng scope dài hơn có thể làm object state cũ hoặc xung đột optimistic lock trở thành vấn đề lớn hơn.

## 13. Transaction propagation và thành phần khác

Trong ứng dụng thực, một JTA transaction có thể được chia sẻ giữa nhiều component/service. Ví dụ một EJB A gọi EJB B, cả hai có transaction attribute REQUIRED, nên B có thể tham gia cùng transaction hiện tại.

Tuy nhiên, **transaction propagation không đồng nghĩa mọi persistence context khác nhau sẽ tự thành một context duy nhất**, và càng không biến một unsynchronized context thành synchronized nếu chưa có bước join phù hợp.

### 13.1. Một context đã được join ở component nào?

Trong ứng dụng container-managed, persistence context có thể được **propagate** theo quy tắc của container cùng JTA transaction. Khi một component nhận context đã được propagate, các quy tắc tương thích giữa persistence unit, scope và synchronization rất quan trọng.

Đừng chủ động thiết kế hai EntityManager với cùng một persistence unit nhưng kỳ vọng chúng luôn mang hai bộ managed entity độc lập trong cùng transaction. Ngược lại, cũng đừng mặc định hai injected fields luôn trỏ tới cùng persistence context. Cần hiểu **quy tắc propagation của container** và lifecycle.

### 13.2. Xung đột synchronized và unsynchronized

Nếu một transaction đã có persistence context gắn với một persistence unit, rồi một component khác muốn dùng context khác với synchronization type không tương thích, container có thể từ chối hoặc ném exception theo quy tắc của JPA/container.

Hướng thiết kế an toàn:

- Xác định component nào **sở hữu vòng đời** extended context.
- Không truyền cùng một context nháp vào những đoạn code mặc định coi context luôn synchronized mà không đánh giá propagation.
- Dùng một chính sách join nhất quán tại điểm bắt đầu nghiệp vụ commit.
- Nếu các service xử lý transaction khác nhau, xem có cần chuyển **ID/DTO** thay vì truyền EntityManager hoặc managed entity qua boundary không.

### 13.3. REQUIRES_NEW không phải cùng transaction

Một method CMT có **REQUIRES_NEW** thường chạy trong JTA transaction mới, tạm ngưng transaction đang có. Việc một extended unsynchronized context từng join T1 **không chứng minh** nó đang tham gia T2. Các thao tác join/flush phải được xét theo transaction hiện tại.

Không đưa một EntityManager dùng chung qua các thread/request song song rồi hy vọng transaction manager tự giải quyết race condition. JTA context liên quan tới execution context, còn EntityManager không thread-safe.

### 13.4. Giao dịch lồng nhau và rollback-only

Nhiều JTA môi trường có cơ chế **rollback-only** thay vì nested database transactions với savepoint tự động. Nếu một service phát sinh PersistenceException khiến transaction bị đánh dấu rollback-only, component khác trong cùng transaction không thể “cứ flush rồi commit” để bỏ qua lỗi.

Một unsynchronized context đã join transaction bị lỗi cần được xử lý theo quy tắc rollback và context lifecycle tương ứng. Không nên dùng lại entity đang managed sau rollback mà không hiểu state của context đó.

## 14. Khi nào provider thực sự phát SQL?

Ngay cả với synchronized context, **tham gia JTA không đồng nghĩa ngay lập tức gửi mọi SQL**.

Một timeline điển hình:

| Hành động | SYNCHRONIZED đã join | UNSYNCHRONIZED chưa join |
|---|---|---|
| em.persist(new Product(...)) | Entity thành managed; SQL INSERT có thể được trì hoãn hoặc chạy sớm do generator | Entity có thể được giữ trong context phù hợp; không tự flush vào JTA |
| Sửa field managed | Pending dirty state | Pending dirty state |
| JPQL query | AUTO có thể flush trước query nếu cần | Không được dựa vào AUTO để tự enlist context |
| em.flush() | Có thể phát DML trong JTA | Không hợp lệ nếu context chưa tham gia |
| JTA commit | Đồng bộ và xác nhận những thay đổi tham gia | Không tự đưa pending changes unjoined vào DB |
| JTA rollback | Hoàn tác DML đã gửi trong transaction | Không tự “xóa” mọi thay đổi trong context sống lâu |

Một thao tác **@GeneratedValue(strategy = IDENTITY)** có thể cần INSERT để lấy ID. Nhưng khi context chưa join JTA, đừng thiết kế ứng dụng dựa vào thời điểm ID xuất hiện hoặc giả định provider được quyền flush vào một transaction mà context không tham gia. Hành vi cấp ID cụ thể phụ thuộc generator/provider.

## 15. Rollback, stale state và optimistic locking

### 15.1. Rollback sau join và flush

~~~java
// Trong một JTA transaction T1 đang hoạt động:
em.joinTransaction();
em.persist(new Product("P-ROLLBACK", "Tên tạm"));
em.flush();

// Transaction manager rollback T1 thay vì commit.
~~~

Nếu INSERT đã được thực thi trong T1, rollback hủy DML chưa commit của T1 theo semantics DB. Tuy nhiên, object Java có thể vẫn chứa generated ID hoặc các trường đã thay đổi; không được khẳng định object đó đã được lưu bền vững.

Sau transaction rollback, trạng thái của extended context cần được xử lý theo đặc tả và nhà cung cấp; không nên tiếp tục submit cùng một bản nháp đã bị flush thất bại mà không xem các entity có còn managed, có bị detach hoặc cần khởi tạo lại không.

### 15.2. Nháp có thể cũ so với database

Giả sử editor mở Product #10 và người dùng chỉnh trong 20 phút. Trong thời gian đó, transaction khác đã cập nhật Product #10.

~~~text
10:00  Editor A tải Product #10 (version=3)
10:05  Editor A sửa displayName, chưa join JTA
10:10  Service B commit Product #10 (version=4)
10:20  Editor A joinTransaction() và flush
~~~

Nếu Product có **@Version**, provider có thể phát hiện optimistic-locking conflict khi cố UPDATE với version cũ. Điểm phát hiện có thể ở flush hoặc commit tùy provider và thao tác.

**UNSYNCHRONIZED không tự giải quyết tranh chấp cập nhật**. Nó chỉ trì hoãn việc tham gia JTA. Khi giữ context sống lâu, càng cần version, quy trình resolve conflict, refresh/reload và UX thông báo dữ liệu đã thay đổi.

### 15.3. @Version không thay thế validation nghiệp vụ

Optimistic locking bảo vệ một nhóm xung đột theo entity version, nhưng không tự xác nhận mã sản phẩm còn unique hoặc số lượng hợp lệ. UNIQUE/FK/CHECK vẫn phải được DB bảo vệ. Validation trước submit có thể bị race condition, nên lỗi constraint tại flush/commit vẫn cần xử lý.

### 15.4. Một điểm dễ nhầm: thao tác chưa join có “rollback” được không?

Nếu một extended unsynchronized context đang giữ pending changes nhưng **chưa join transaction nào**, việc rollback một JTA transaction không liên quan **không phải lệnh hoàn tác mọi thay đổi trong bộ nhớ context đó**. Khi người dùng hủy nháp, ứng dụng cần **kết thúc context/cancel workflow** hoặc có cơ chế tái tạo trạng thái sạch theo kiến trúc, thay vì gọi rollback trên transaction mà context chưa tham gia.

Đây là khác biệt quan trọng giữa:

- **rollback một transaction DB**;
- **discard những thay đổi trong persistence context chưa từng tham gia transaction**.

Hai trách nhiệm không thể đánh đồng.

## 16. Quyền và ngoại lệ liên quan tới transaction

Các API JPA/JTA có giới hạn rõ:

### 16.1. Không dùng EntityManager.getTransaction() trên JTA EntityManager

~~~java
// Không dùng cách sau với JTA-managed EntityManager:
// em.getTransaction().begin();
// em.getTransaction().commit();
~~~

**EntityTransaction** là API giao dịch cho RESOURCE_LOCAL. Với JTA EntityManager, transaction do container, UserTransaction (nếu môi trường cho phép) hoặc framework/JTA transaction manager quản lý. Việc gọi **getTransaction()** trên JTA EntityManager không phải cách hợp lệ để điều khiển transaction và có thể gây **IllegalStateException**.

### 16.2. Không có JTA transaction khi join

~~~java
// Khi không có JTA transaction đang hoạt động:
em.joinTransaction();
~~~

joinTransaction() không tạo JTA transaction; ứng dụng phải có một transaction thích hợp trước. Theo ngữ nghĩa API, việc yêu cầu join khi không có transaction hợp lệ có thể dẫn đến **TransactionRequiredException**.

### 16.3. Flush không có transaction được tham gia

Nếu context chưa tham gia transaction JTA phù hợp và application gọi **em.flush()**, JPA có thể ném **TransactionRequiredException**. Đây là một dấu hiệu thường gặp khi dùng UNSYNCHRONIZED nhưng quên join.

### 16.4. Lỗi database ở flush

Sau khi join và flush, DB có thể báo:

- UNIQUE violation do mã sản phẩm trùng;
- FOREIGN KEY violation do quan hệ không hợp lệ;
- NOT NULL/CHECK violation;
- OptimisticLockException do version cũ;
- Deadlock hoặc timeout.

Những lỗi này không chứng minh synchronization type sai. Chúng có thể xuất hiện **sớm hơn commit** do flush thực sự chạy SQL. Khi persistence operation thất bại, transaction có thể rollback-only và context có thể không còn an toàn để tiếp tục.

### 16.5. Callback không phải afterCommit

**@PrePersist/@PostPersist**, **@PreUpdate/@PostUpdate** có thể chạy trong quá trình flush trước khi JTA commit. Không gửi email hoặc sự kiện bên ngoài rồi cho rằng “Post” nghĩa là dữ liệu đã commit.

Nếu cần publish event sau khi database xác nhận, cân nhắc **transactional outbox** hoặc transaction-aware callback phù hợp; việc gửi sau commit còn cần retry nếu hệ thống ngoài tạm thời không khả dụng.

## 17. Transaction-scoped unsynchronized có phù hợp cho mọi workflow không?

Một cái bẫy thiết kế:

~~~text
HTTP Request 1:
  inject transaction-scoped UNSYNCHRONIZED EM
  em.persist(draft)
  không join
  request kết thúc

HTTP Request 2:
  inject một EM khác
  em.joinTransaction()
  mong draft của request 1 tự xuất hiện
~~~

Điều này **không được bảo đảm**. Persistence context scope và lifecycle quyết định các managed objects có còn không. Một request mới không tự nhận lại managed entity của context cũ chỉ vì có cùng persistence unit.

Với draft kéo dài qua nhiều request, các lựa chọn kiến trúc gồm:

1. **Extended unsynchronized context** gắn với một component có lifecycle phù hợp, ví dụ stateful session bean.
2. **Lưu nháp thật vào DB** trong transaction riêng, đánh dấu trạng thái DRAFT rồi chuyển sang FINAL theo nghiệp vụ.
3. **Giữ DTO nháp ở tầng ứng dụng/khách hàng**, và chỉ tạo/update entity tại transaction Submit.

Hai phương án cuối thường đơn giản hơn trong hệ thống web stateless, nhiều node hoặc cần khôi phục nháp sau restart. Extended persistence context không phải kho lưu trữ bền vững: nếu process bị dừng và không có cơ chế bảo toàn session phù hợp, state chưa commit có thể mất.

### 17.1. Sự khác nhau giữa nháp trong context và nháp đã commit

| Đặc tính | Nháp chưa join trong extended context | Nháp DRAFT đã commit trong DB |
|---|---|---|
| Có hàng DB đã commit | Chưa | Có |
| Có thể phục hồi sau process restart | Không được tự bảo đảm | Có, theo khả năng DB |
| Có thể chia sẻ giữa nhiều service | Khó, phụ thuộc component/session | Dễ hơn theo ID và transaction |
| Cần xử lý stale data | Có | Có |
| Hủy nháp | Kết thúc/discard context | Transaction xóa/đánh dấu hủy theo nghiệp vụ |
| Phù hợp nhiều bước ngắn trong cùng phiên | Có thể | Có |
| Phù hợp quy trình nhiều ngày | Cần cân nhắc rất kỹ | Thường dễ vận hành hơn |

Không có lựa chọn nào thay thế thiết kế quyền truy cập, validation, optimistic locking và idempotency ở tầng nghiệp vụ.

## 18. Trộn JPA với JDBC, JTA và transaction của hệ khác

Một tình huống điển hình:

~~~java
em.persist(product);
em.joinTransaction();
em.flush();

// Sau đó dùng một JDBC connection khác để SELECT.
~~~

Nếu connection khác **không tham gia cùng JTA transaction**, nó có thể không nhìn thấy DML chưa commit do isolation. **em.flush() không khiến mọi JDBC connection bên ngoài thấy được thay đổi**.

Để phối hợp đúng:

- DataSource/JDBC connection phải được quản lý và enlisted vào **cùng JTA transaction** nếu cần cùng một đơn vị công việc.
- Không tự tạo connection ngoài transaction manager rồi tưởng nó được tự động enlist.
- Với nhiều resource, kiểm tra khả năng XA, enlistment, recovery và các giới hạn của transaction manager.
- Kafka, HTTP, email, file system không tự có atomic commit chỉ vì EntityManager đã join JTA.
- Nếu việc phát sự kiện cần nhất quán với dữ liệu DB, cân nhắc outbox thay vì phát trực tiếp trước commit.

**SynchronizationType** của JPA không phải công cụ tự động giải quyết distributed transaction.

## 19. Quan sát trong runtime: log và phép thử

Để phân biệt các trường hợp, cần log mốc:

~~~text
[A] JTA transaction bắt đầu
[B] EntityManager.isJoinedToTransaction() = false
[C] em.persist(Product)
[D] em.joinTransaction()
[E] EntityManager.isJoinedToTransaction() = true
[F] em.flush()
[G] SQL INSERT ...
[H] JTA transaction commit
~~~

Với một synchronized EntityManager, trạng thái joined có thể đã true khi nó tham gia JTA. Với unsynchronized, thường chuyển sang true khi joinTransaction() thành công.

### 19.1. SQL logging có kiểm soát

Hibernate và EclipseLink có cơ chế SQL logging riêng. Tên thuộc tính hoặc logger thay đổi theo provider/version. Ví dụ thuộc tính của Hibernate:

~~~properties
hibernate.show_sql=true
hibernate.format_sql=true
~~~

Đây không phải thuộc tính chuẩn Jakarta Persistence. Nếu dùng EclipseLink, cần cấu hình logging tương ứng của EclipseLink. Để kiểm tra ranh giới transaction, SQL log thuần đôi khi chưa đủ: cần log từ transaction manager hoặc JDBC instrumentation.

Không bật logging bind parameters chứa dữ liệu nhạy cảm trên production nếu chưa có kiểm soát thích hợp.

### 19.2. Phép thử tích hợp cơ bản

Với một JTA test environment đủ khả năng tạo UserTransaction và EntityManagerFactory, có thể kiểm tra chuỗi:

~~~java
EntityManager em =
    emf.createEntityManager(SynchronizationType.UNSYNCHRONIZED);

try {
    utx.begin();

    Product p = new Product("TEST-220", "Unsync JTA");
    em.persist(p);

    boolean notJoinedYet = !em.isJoinedToTransaction();

    em.joinTransaction();
    boolean joinedNow = em.isJoinedToTransaction();
    if (!joinedNow) {
        throw new AssertionError("Expected joined persistence context");
    }

    em.flush();
    Long id = p.getId();
    if (id == null) {
        throw new AssertionError("ID not allocated after flush");
    }

    utx.commit();
} finally {
    em.close();
}
~~~

Ví dụ này minh họa **happy path** và giả định có transaction manager/JTA datasource, sequence, schema và xử lý rollback phù hợp trong test harness. Trong test thực, cần dùng try/catch để rollback khi lỗi; có thể tái sử dụng mẫu xử lý UserTransaction ở phần 9.

Một phép thử riêng có thể gọi **em.flush() trước joinTransaction()** trong một transaction mới và xác nhận **TransactionRequiredException**. **Không nên tiếp tục dùng transaction vừa chịu exception**; rollback và tạo lại context cho test khác.

### 19.3. Những tình huống nên thử

| Phép thử | Điều cần quan sát |
|---|---|
| Synchronized + transaction active | Context tham gia JTA phù hợp, commit ghi dữ liệu |
| Unsynchronized + transaction active, chưa join | Không mặc nhiên flush pending changes khi JTA commit |
| Unsynchronized + join + flush | DML được đồng bộ vào JTA hiện tại |
| Unsynchronized + flush trước join | Exception phù hợp với contract |
| Unsynchronized extended qua hai lời gọi | State còn theo lifecycle stateful component |
| Sau join rồi rollback | Không có DML đã commit; state object cần xử lý |
| Hai transaction cùng sửa một entity | @Version/optimistic conflict theo provider |
| Dùng hai JTA transactions khác nhau | Không mặc định context tham gia transaction mới |
| Query trước và sau join/flush | Phân biệt pending state với dữ liệu đã đồng bộ |
| Kết hợp JDBC connection riêng | Phân biệt resource có enlist vào cùng JTA hay không |
| Resource_LOCAL dùng API synchronization JTA | Không nhầm mô hình giao dịch |
| Lỗi constraint tại flush | Transaction rollback và scope được dọn an toàn |

### 19.4. Kiểm tra commit thực sự

Đừng chỉ nhìn **Product.getId() != null** sau flush để kết luận đã lưu thành công. Có thể ID đã được cấp nhưng transaction sau đó rollback. Cần:

1. Commit JTA transaction thành công.
2. Mở transaction/EntityManager mới độc lập.
3. Đọc lại bằng khóa chính.
4. Xác nhận dữ liệu đúng và thực sự đã commit.

Trong phép thử có database sạch, nên dọn dữ liệu test bằng transaction riêng. Không giả định rollback trả lại sequence value.

## 20. Troubleshooting: triệu chứng và cách tiếp cận

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| commit xong không thấy dữ liệu nháp | Context UNSYNCHRONIZED chưa join | Kiểm tra em.isJoinedToTransaction(), joinTransaction và scope |
| em.flush() ném TransactionRequiredException | Chưa có JTA transaction hoặc context chưa join | Kiểm tra transaction manager và join |
| em.getTransaction() báo lỗi | EntityManager dùng JTA, không phải RESOURCE_LOCAL | Dùng CMT/@Transactional/UserTransaction hợp lệ |
| joinTransaction() không hợp lệ | Không có active JTA hoặc EntityManager sai trạng thái | Kiểm tra transaction hiện tại, EM lifecycle |
| EntityManager không còn nháp ở request sau | Context transaction-scoped đã kết thúc | Dùng extended đúng lifecycle hoặc nháp lưu DB/DTO |
| Dữ liệu nháp bất ngờ được flush | Extended SYNCHRONIZED đã tham gia JTA ngoài ý định | Kiểm tra synchronization và transaction propagation |
| JOINED nhưng SQL chưa thấy UPDATE | Có thể dirty state chưa flush | Kiểm tra flush mode, join và SQL log |
| Cập nhật thất bại ở submit do version | Context giữ dữ liệu cũ quá lâu | @Version, reload và xử lý conflict |
| Constraint chỉ báo lỗi khi submit | DML chưa chạy cho tới join/flush | Validation sớm và xử lý DB violation |
| Sau rollback object vẫn có ID | ID cấp trước commit | Không dùng ID như bằng chứng đã commit |
| JDBC connection ngoài không thấy INSERT đã flush | Connection khác transaction hoặc isolation | Kiểm tra enlistment JTA và DataSource |
| Cache chứa state cũ | Long-lived context và dữ liệu DB thay đổi ở nơi khác | Refresh/reload theo scope và policy |
| “Already associated”/context conflict | Nhiều context/propagation không tương thích | Rà soát persistence unit, type và synchronization |
| Transaction bị rollback-only sau exception | Lỗi flush/constraint/JTA | Rollback, kết thúc scope lỗi và xử lý lại có kiểm soát |
| SQL chạy sớm dù mới persist | Generator hoặc provider thực thi SQL để cấp ID/đồng bộ | Xem strategy, SQL và transaction log |

Khi gặp lỗi, cần xác định **transaction type**, **persistence context scope**, **synchronization type**, **điểm join**, **flush mode** và **provider/dialect** trước khi sửa annotation. Một lỗi “không ghi DB” có thể do context chưa join, do transaction rollback hoặc do schema/constraint; không nên quy mọi lỗi về UNSYNCHRONIZED.

## 21. Các hiểu nhầm thường gặp

### 21.1. “Có JTA transaction là mọi EntityManager đều tự tham gia”

Sai. UNSYNCHRONIZED cho phép context không tự join. Hãy gọi **joinTransaction()** tại điểm thực sự muốn đồng bộ.

### 21.2. “UNSYNCHRONIZED là chế độ chỉ đọc”

Sai. Mục tiêu của nó là **điều khiển việc tham gia JTA**, không biến context thành read-only. Context có thể giữ pending changes phù hợp với lifecycle, rồi flush sau khi join.

### 21.3. “UNSYNCHRONIZED nghĩa là FlushModeType.COMMIT”

Sai. FlushModeType.COMMIT vẫn mô tả hành vi flush đối với query trong một context **đã tham gia transaction**; không tự hủy hoặc tạo quan hệ JTA.

### 21.4. “joinTransaction() sẽ commit ngay”

Sai. Join chỉ tham gia transaction; flush/commit là các bước khác.

### 21.5. “Mỗi lần gọi persist() đều SQL INSERT ngay”

Không bảo đảm. Provider có thể trì hoãn INSERT hoặc cần SQL cấp ID sớm. IDENTITY và SEQUENCE có hành vi khác nhau.

### 21.6. “Sửa object trong extended context là dữ liệu đã an toàn”

Sai. State trong bộ nhớ không phải dữ liệu DB đã commit, và extended context không tự là kho nháp bền vững qua crash/restart.

### 21.7. “rollback một JTA bất kỳ sẽ xóa nháp đang unjoined”

Sai. Rollback không phải lệnh dọn toàn bộ state của context chưa tham gia transaction đó.

### 21.8. “SYNCHRONIZED luôn flush ở mỗi query”

Không đúng. FlushModeType.AUTO cho phép provider đồng bộ khi cần để đảm bảo kết quả; flush không có nghĩa mọi SELECT đều phải sinh UPDATE.

### 21.9. “Một EntityManager có thể dùng đồng thời từ nhiều thread”

Sai. Không chia sẻ EntityManager hoặc extended context cho nhiều thread ghi cạnh tranh. Dùng scope và transaction boundary phù hợp.

### 21.10. “@PostPersist nghĩa là database đã commit”

Sai. Callback có thể xảy ra tại flush trước commit. Side effects ngoài DB phải được điều phối theo transaction.

### 21.11. “Context unsynchronized tự giữ nháp qua mọi HTTP request”

Sai. Scope của context mới quyết định vòng đời. Transaction-scoped context không tự biến thành extended do UNSYNCHRONIZED.

### 21.12. “joinTransaction() có thể dùng thay mọi cơ chế transaction”

Sai. Nó không mở/commit transaction, không cấp quyền resource, không sửa lỗi datasource hoặc isolation và không tự giải quyết transaction phân tán.

## 22. Cách lựa chọn trong ứng dụng thực tế

| Nhu cầu | Lựa chọn thường phù hợp |
|---|---|
| CRUD thông thường: mỗi request ghi và commit | Transaction-scoped SYNCHRONIZED |
| Service gọi nhiều repository trong một JTA | Synchronized, transaction propagation nhất quán |
| Soạn nháp ngắn nhiều bước cùng một stateful component | Extended UNSYNCHRONIZED, join ở Submit |
| Web stateless nhiều node, nháp cần tồn tại sau restart | Lưu nháp DB hoặc DTO riêng; không chỉ dựa vào extended context |
| Cần trì hoãn flush trước query nhưng vẫn tự join | SYNCHRONIZED + FlushModeType.COMMIT nếu semantics phù hợp |
| Cần quyết định có tham gia JTA hay không | UNSYNCHRONIZED + joinTransaction() |
| Cần commit cùng nhiều resource | JTA transaction manager/datasource/resource enlistment phù hợp |
| Cần external event sau commit | Outbox hoặc transaction-aware event mechanism |

**Khuyến nghị thiết kế:** ứng dụng CRUD thông thường ít lý do cần UNSYNCHRONIZED. Đây là một cơ chế nâng cao, hữu ích khi cần **giữ và điều phối state trong persistence context độc lập với thời điểm tham gia một JTA transaction cụ thể**.

## 23. Bài tập thực hành

### Bài 1: Hai annotation có ý nghĩa gì?

~~~java
@PersistenceContext(
    type = PersistenceContextType.EXTENDED,
    synchronization = SynchronizationType.UNSYNCHRONIZED
)
private EntityManager em;
~~~

**Câu hỏi:** EXTENDED và UNSYNCHRONIZED có phải cùng một khái niệm không?

**Đáp án:** Không. EXTENDED chỉ vòng đời context kéo dài qua các transaction theo lifecycle component; UNSYNCHRONIZED chỉ việc context không auto join JTA.

### Bài 2: Không thấy INSERT sau commit

Một method @Transactional persist vào unsynchronized context rồi return mà không join. Transaction manager commit thành công nhưng DB không thấy bản ghi mới.

**Câu hỏi:** Có thể giải thích thế nào?

**Đáp án:** Context chưa tham gia transaction nên pending changes không tự flush vào JTA đó. Cần đánh giá context lifecycle và chủ động joinTransaction() trong một transaction phù hợp trước khi muốn commit.

### Bài 3: flush() trước join

~~~java
// Có JTA T1 nhưng context UNSYNCHRONIZED chưa join:
em.persist(product);
em.flush();
~~~

**Câu hỏi:** Vì sao có thể có TransactionRequiredException dù “transaction đang chạy”?

**Đáp án:** EntityManager không chỉ cần một transaction tồn tại đâu đó; persistence context phải **tham gia transaction phù hợp**. UNSYNCHRONIZED chưa join thì flush không hợp lệ.

### Bài 4: JTA hay RESOURCE_LOCAL?

Ứng dụng khai báo persistence unit JTA rồi gọi:

~~~java
em.getTransaction().begin();
~~~

**Câu hỏi:** Sai ở đâu?

**Đáp án:** EntityTransaction dùng cho resource-local. Với JTA, dùng container-managed transaction, @Transactional hoặc UserTransaction ở môi trường cho phép.

### Bài 5: Soạn nháp 10 phút

Người dùng mở form, thêm 5 dòng, sửa 3 lần rồi nhấn Submit. Team muốn giữ managed entity xuyên các bước và chưa ghi DB cho tới Submit.

**Câu hỏi:** Cấu hình nào là ứng viên?

**Đáp án:** Extended unsynchronized context gắn với một stateful component có lifecycle rõ; các bước thay đổi state không join, Submit mở JTA và gọi joinTransaction(). Cần cân nhắc timeout, memory và stale data. Với web stateless, lưu DTO nháp hoặc bảng DRAFT có thể đáng tin cậy hơn.

### Bài 6: Extended synchronized làm lộ thay đổi nháp

Một editor dùng EXTENDED SYNCHRONIZED. Trong khi user chưa bấm Lưu, một method khác có JTA transaction được gọi trên cùng component và provider flush các pending changes.

**Câu hỏi:** Vì sao có thể xảy ra?

**Đáp án:** EXTENDED chỉ kéo dài vòng đời context. SYNCHRONIZED vẫn có thể tự tham gia transaction phù hợp và đồng bộ state. Nếu cần “chỉ commit khi Submit”, phải thiết kế transaction boundary và synchronization cẩn thận.

### Bài 7: Context giữ dữ liệu cũ

Editor A tải Product version 7 rồi chỉnh trong extended unsynchronized context. Transaction B cập nhật cùng Product thành version 8. A sau đó join và flush.

**Câu hỏi:** Rủi ro gì?

**Đáp án:** Có thể xảy ra optimistic locking conflict. UNSYNCHRONIZED không ngăn transaction khác cập nhật DB và không tự refresh entity. Cần @Version, xử lý conflict và có thể tải lại dữ liệu.

### Bài 8: Flush thành công rồi rollback

~~~java
em.joinTransaction();
em.persist(product);
em.flush();
// Một lỗi nghiệp vụ đánh dấu JTA rollback-only.
~~~

**Câu hỏi:** Có chắc product đã lưu bền vững?

**Đáp án:** Không. SQL có thể đã chạy nhưng transaction chưa commit. Rollback có thể hoàn tác DML, trong khi ID đã cấp hoặc side effect ngoài DB có thể không quay lại.

### Bài 9: Hai datasource

EntityManager đã join JTA và flush một INSERT, nhưng code dùng JDBC connection độc lập từ datasource khác không thấy hàng mới.

**Câu hỏi:** Có phải flush thất bại?

**Đáp án:** Không nhất thiết. Connection kia có thể không enlisted trong cùng JTA transaction hoặc isolation không cho đọc dữ liệu chưa commit. Cần kiểm tra transaction manager, datasource và connection scope.

### Bài 10: Chọn flush mode

Một developer đặt **em.setFlushMode(FlushModeType.AUTO)** trên unsynchronized context rồi cho rằng query sẽ tự flush mọi thay đổi vào JTA dù chưa join.

**Câu hỏi:** Nhận định đúng không?

**Đáp án:** Không. AUTO điều khiển việc bảo đảm kết quả query trong phạm vi đồng bộ hợp lệ; không thay thế **joinTransaction()**.

### Bài 11: Transaction mới sau một lần join

Extended unsynchronized context đã join và commit T1. Sau đó một method khác mở T2, sửa một entity managed rồi muốn flush.

**Câu hỏi:** Có thể mặc định context đang tham gia T2 vì từng tham gia T1 không?

**Đáp án:** Không nên mặc định. Cần xác định transaction hiện tại và thực hiện join theo contract/lifecycle, kiểm tra isJoinedToTransaction() khi phù hợp.

### Bài 12: Callback và external event

Một @PostPersist listener gửi email xác nhận. Product được flush trong JTA T1, nhưng T1 rollback do một entity khác vi phạm FK.

**Câu hỏi:** Email có tự rollback không?

**Đáp án:** Không. Callback có thể chạy trước JTA commit và email nằm ngoài transaction DB. Cần cơ chế afterCommit/outbox với retry nếu yêu cầu nhất quán.

## 24. Ghi nhớ

**SYNCHRONIZED** và **UNSYNCHRONIZED** trong JPA trả lời câu hỏi *persistence context tham gia JTA lúc nào*, không phải *entity có được phép đọc/ghi hay không* hoặc *transaction được commit ra sao*.

Tóm lược luồng:

~~~text
SYNCHRONIZED:
  JTA active -> context tham gia phù hợp
             -> flush khi cần
             -> JTA commit/rollback

UNSYNCHRONIZED:
  context giữ managed state
          -> JTA active (chưa auto join)
          -> em.joinTransaction()
          -> flush khi cần
          -> JTA commit/rollback
~~~

Khi thiết kế, phải xem cùng lúc **JTA transaction type**, **TRANSACTION hay EXTENDED context**, **SynchronizationType**, **FlushModeType** và **lifecycle của component**. Một extended unsynchronized context rất hữu ích cho bài toán soạn nháp có kiểm soát, nhưng cần chủ động join, quản lý dữ liệu cũ, rollback và tài nguyên. Với CRUD giao dịch thông thường, transaction-scoped synchronized context vẫn là lựa chọn đơn giản, rõ ràng và dễ vận hành hơn.

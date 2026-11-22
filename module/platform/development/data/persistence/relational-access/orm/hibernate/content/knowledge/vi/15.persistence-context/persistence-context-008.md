# Session tồn tại lâu, bộ nhớ tăng và dữ liệu bị cũ trong Hibernate ORM

## 1. Bối cảnh: một Session không phải kho dữ liệu vô hạn

Hãy hình dung hệ thống thương mại điện tử có các thực thể **Customer**, **PurchaseOrder**, **OrderItem** và **Product**. Ban đầu ứng dụng chỉ xử lý một đơn hàng trong mỗi HTTP request, Hibernate hoạt động bình thường. Sau đó nhóm phát triển bổ sung công việc hàng đêm:

- Đọc 300.000 đơn hàng chưa đồng bộ.
- Chuẩn hóa trạng thái của từng đơn.
- Gửi dữ liệu sang một hệ thống bên ngoài.
- Ghi lại thời điểm đã đồng bộ.

Một lập trình viên đặt toàn bộ vòng lặp trong **@Transactional** và dùng **findAll()** để lấy danh sách. Chương trình ban đầu chạy được nhưng sau nhiều phút heap sử dụng tăng, garbage collector hoạt động liên tục, thời gian flush kéo dài hoặc cuối cùng gặp **OutOfMemoryError**.

Một lỗi khác xuất hiện ở màn hình quản trị: cùng một EntityManager/Session được giữ quá lâu. Nhân viên A cập nhật trạng thái đơn hàng và commit, nhân viên B truy vấn cùng bản ghi qua Session cũ nhưng vẫn nhìn thấy trạng thái trước đó.

Hai hiện tượng này có chung một yếu tố: **persistence context cấp một (first-level cache) tồn tại lâu và giữ state của những entity đã được quản lý**.

Trong Hibernate ORM, việc một Session tồn tại lâu không tự nó luôn gây lỗi. Vấn đề là **Session tích lũy quá nhiều entity/collection**, hoặc **ứng dụng tưởng dữ liệu được làm mới sau mỗi lần query trong khi persistence context vẫn giữ object cũ**.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt **Session**, **EntityManager**, **persistence context**, transaction và JDBC connection.
2. Giải thích vì sao số entity managed tăng làm tăng heap, chi phí dirty checking và thời gian flush.
3. Hiểu vì sao gọi **find()** hai lần trong cùng persistence context có thể trả lại cùng object dù DB đã thay đổi.
4. Sử dụng có chủ đích **flush()**, **clear()**, **detach()/evict()**, **refresh()** và transaction boundary.
5. Xử lý batch theo từng phần để tránh giữ hàng trăm nghìn entity trong cùng một Session.
6. Tổ chức **@Transactional**, **spring.jpa.open-in-view**, streaming và tác vụ chạy lâu đúng phạm vi.
7. Phân biệt dữ liệu cũ trong persistence context với cache cấp hai, isolation level và optimistic locking.
8. Quan sát và kiểm thử vấn đề bộ nhớ/dữ liệu cũ bằng SQL log, Hibernate Statistics và phép thử tích hợp.

Ví dụ dùng Java 17+, Jakarta Persistence (package **jakarta.persistence**), Hibernate ORM 6.x, Spring Boot 3.x và PostgreSQL. Các chiến lược chính có thể áp dụng cho ứng dụng Hibernate thuần; tên cấu hình và chi tiết API nâng cao có thể khác tùy version.

## 2. Những đối tượng có vòng đời khác nhau

Trước khi xử lý Session tồn tại lâu, cần tránh nhầm lẫn các lớp trách nhiệm:

| Thành phần | Vai trò | Vòng đời thông thường |
|---|---|---|
| **SessionFactory / EntityManagerFactory** | Factory quản lý metadata mapping, tạo Session/EntityManager | Dùng chung dài hạn trong ứng dụng; được thiết kế để chia sẻ giữa thread |
| **Session / EntityManager** | Unit of work với persistence context, API đọc/ghi entity | Thường ngắn, gắn một thao tác/transaction hoặc scope được quản lý |
| **Persistence context** | Tập entity managed theo identity và trạng thái theo dõi | Gắn với EntityManager/Session; có thể sống qua nhiều transaction nếu cố tình mở rộng |
| **Transaction** | Ranh giới commit/rollback và tính nguyên tử của thao tác DB | Nên ngắn theo một use case hoặc một batch |
| **JDBC connection** | Kết nối vật lý/logical tới database qua pool | Có thể được cấp phát và trả pool theo chế độ quản lý connection |
| **HTTP request** | Ranh giới giao tiếp với client | Có thể chứa một hoặc nhiều use case/transaction; không mặc nhiên là transaction |

**Session không đồng nghĩa JDBC connection.** Một Session có thể còn mở nhưng chưa giữ connection trong suốt thời gian tồn tại; Hibernate có những chế độ cấp phát/giải phóng connection khác nhau. Ngược lại, một transaction dài có thể giữ lock hoặc connection lâu dù số entity trong cache ít.

**Session cũng không đồng nghĩa transaction.** Cách ứng dụng cấu hình có thể cho Session tồn tại qua nhiều transaction. Đó là nguồn thường gặp của dữ liệu cũ và state tồn đọng.

~~~mermaid
flowchart TD
    SF[SessionFactory - dùng chung] --> S1[Session A]
    SF --> S2[Session B]
    S1 --> PC1[Persistence context A]
    S2 --> PC2[Persistence context B]
    PC1 --> A1[Customer #10]
    PC1 --> A2[Order #51]
    PC1 --> A3[Order #52]
    PC2 --> B1[Customer #10 - instance khác]
    S1 -. SQL trong transaction .-> DB[(Database)]
    S2 -. SQL trong transaction .-> DB
~~~

Hai Session có thể quản lý **hai Java object khác nhau cho cùng một hàng** Customer #10. Việc Session A cập nhật object của mình không tự cập nhật object Customer #10 trong Session B.

## 3. First-level cache: Hibernate ghi nhớ entity nào?

Mỗi persistence context có cơ chế **identity map**: với một entity type và identifier cụ thể, trong một context thông thường chỉ có một managed instance tương ứng. Khi gọi:

~~~java
Customer first = entityManager.find(Customer.class, 10L);
Customer second = entityManager.find(Customer.class, 10L);

System.out.println(first == second); // true trong cùng persistence context
~~~

Hibernate có thể dùng object đã managed cho lần đọc thứ hai mà không cần query SQL nữa. Điều này hữu ích:

- Giữ tính nhất quán object graph trong một unit of work.
- Tránh đọc lặp lại cùng entity không cần thiết.
- Theo dõi thay đổi và tự flush qua dirty checking.
- Quản lý quan hệ, proxy và cascades theo cùng ranh giới.

Nhưng first-level cache **không phải cache tự hết hạn sau vài giây**. Khi persistence context còn giữ entity managed, Hibernate không mặc định đuổi entity cũ ra theo TTL, số lượng hoặc dung lượng heap. Một local variable ra khỏi scope **không có nghĩa** entity được giải phóng nếu persistence context vẫn tham chiếu đến nó.

### 3.1. Vòng đời entity liên quan đến memory

~~~mermaid
flowchart LR
    N[Transient - new] -->|persist| M[Managed]
    D[Detached] -->|merge trả managed copy| M
    M -->|detach / clear / close| D
    M -->|remove| R[Removed]
    R -->|flush/commit| X[(Hàng bị xóa)]
    M -->|dirty checking và flush| DB[(SQL INSERT/UPDATE)]
~~~

Một entity **managed** được Hibernate theo dõi. Một entity **detached** vẫn là object Java hợp lệ nhưng không còn được persistence context cũ theo dõi. **clear()** và **detach()** chuyển trạng thái quản lý, không tự xóa object khỏi bộ nhớ nếu code của bạn vẫn giữ tham chiếu trong List, Map, queue hoặc biến singleton.

### 3.2. Hibernate còn lưu những gì ngoài entity?

Tùy mapping và cơ chế Hibernate, persistence context có thể giữ:

- Các instance entity managed được tra theo entity key/ID.
- Thông tin entry/state giúp theo dõi trạng thái và phiên bản entity.
- Snapshot của thuộc tính đã tải phục vụ dirty checking; một số cấu hình read-only/enhancement có thể thay đổi cách theo dõi.
- Collection wrapper và snapshot của collection persistent.
- Proxy và thông tin để khởi tạo lazy association.
- Pending actions của các thao tác INSERT/UPDATE/DELETE chưa flush.

Vì vậy một đơn hàng có 10 dòng, mỗi dòng tham chiếu một sản phẩm, có thể kéo theo nhiều object và metadata hơn một bản ghi PurchaseOrder đơn lẻ. Nếu code join fetch nhiều collection, số object được tạo/giữ còn tăng mạnh.

## 4. Vì sao Session tồn tại lâu làm heap tăng?

Xét một service chạy import như sau:

~~~java
@Service
public class BadOrderMaintenanceService {
    private final PurchaseOrderRepository orders;

    public BadOrderMaintenanceService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void normalizeAll() {
        List<PurchaseOrder> all = orders.findAll();
        for (PurchaseOrder order : all) {
            order.normalizeStatus();
        }
    }
}
~~~

Ví dụ trên giả định entity có method **normalizeStatus()**. Vấn đề không nằm ở tên method, mà ở hai hành vi:

1. **findAll()** đưa toàn bộ dữ liệu vào một List rất lớn.
2. Entity được load trong **cùng một persistence context** và có thể vẫn được Hibernate quản lý tới lúc transaction kết thúc.

Trong batch 300.000 đơn, ứng dụng có thể giữ đồng thời List Java, hàng trăm nghìn entity, snapshot, collection/proxy và action queue. Khi gần cuối, dirty checking và flush phải xử lý lượng state lớn. Heap tăng, GC liên tục và transaction kéo dài.

### 4.1. Thay findAll bằng từng query nhưng vẫn dùng cùng Session

Một biến thể trông có vẻ cải thiện:

~~~java
@Transactional
public void normalizeAll() {
    for (long id = 1; id <= 300_000; id++) {
        PurchaseOrder order = entityManager.find(PurchaseOrder.class, id);
        if (order != null) {
            order.normalizeStatus();
        }
    }
}
~~~

Đoạn này không giữ một List 300.000 phần tử. Tuy nhiên **mỗi entity tìm được vẫn có thể vào persistence context**. Nếu không clear/detach hoặc kết thúc context, state được quản lý tiếp tục tích lũy. Ngoài ra, code phát sinh rất nhiều truy vấn theo ID và không xử lý tốt ID bị thiếu/nhảy số.

Giảm số object được giữ bởi **một biến Java** không nhất thiết giảm số object mà **Hibernate** còn giữ.

### 4.2. Chi phí không chỉ là memory

| Hiện tượng | Cơ chế thường gặp | Hệ quả |
|---|---|---|
| Heap tăng dần | Entity, loaded-state, collection, action queue tích lũy | GC pressure, OutOfMemoryError |
| Flush chậm dần | Nhiều entity/collection cần kiểm tra và đồng bộ | Thời gian commit tăng |
| Transaction quá dài | Một transaction giữ hàng trăm nghìn thay đổi | Lock dài, log/WAL lớn, rollback tốn kém |
| SQL phát sinh bất ngờ | Lazy associations hoặc flush tự động | Số statement cao, N+1 |
| Dữ liệu bị cũ | Object managed được tái sử dụng trong PC lâu | Logic dựa vào state cũ |
| Lỗi khi cuối batch | Constraint, deadlock, lock timeout phát hiện muộn | Phải rollback công việc lớn |

Mỗi nguyên nhân có cách sửa khác nhau: **clear()** có thể giảm số entity managed, nhưng không rút ngắn một transaction; chia transaction giúp giới hạn thời gian transaction, nhưng không hiệu quả nếu code ngoài vẫn giữ toàn bộ List trong bộ nhớ.

## 5. Flush, clear, detach, refresh và close: tác động khác nhau

Hibernate/JPA cung cấp nhiều thao tác. Chúng không phải những tên thay thế cho nhau:

| Thao tác | Tác động chính | Có ghi SQL pending? | Có làm entity rời persistence context? |
|---|---|---|---|
| **flush()** | Đồng bộ state hiện tại thành SQL trong transaction | Có, khi có thay đổi cần đồng bộ | **Không** |
| **clear()** | Detach tất cả entity trong persistence context | **Không tự flush** | **Có**, với mọi managed entity |
| **detach(entity)** / Hibernate **evict(entity)** | Dừng quản lý một entity cụ thể | Không tự flush | **Có**, riêng entity được chỉ định |
| **refresh(entity)** | Nạp lại state từ DB vào managed entity | Không mang nghĩa commit; có thể tương tác flush mode | **Không** |
| **close()** | Đóng EntityManager/Session; kết thúc scope quản lý | Không phải thao tác commit | Context hết hiệu lực; object cũ không còn managed ở đó |
| **commit()** | Hoàn tất transaction sau khi đồng bộ thích hợp | Thường flush trước commit | Không nhất thiết đóng một extended Session |

**Hai nhầm lẫn nguy hiểm nhất:**

- Gọi **flush()** nhiều lần nhưng **không clear()**: các entity vẫn managed và có thể tiếp tục chiếm heap.
- Gọi **clear()** khi còn thay đổi chưa flush: pending state không được đồng bộ có thể bị mất, tùy trạng thái thao tác và flush đã diễn ra trước đó.

### 5.1. Flush không đồng nghĩa commit

~~~java
entityManager.persist(order);
entityManager.flush(); // SQL INSERT có thể đã chạy, transaction vẫn mở.
// Nếu transaction sau đó rollback, dữ liệu đã flush bị rollback.
~~~

Flush làm Hibernate gửi SQL cần thiết để đồng bộ state với database **trong transaction hiện tại**. Không vì thấy INSERT trong log mà kết luận dữ liệu đã được commit và đọc được từ transaction khác.

### 5.2. Clear không có nghĩa xóa dữ liệu DB

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
order.changeNote("đã đối soát");
em.clear(); // Nếu chưa flush, Hibernate không còn theo dõi thay đổi này.
~~~

Từ sau clear, **order** vẫn là object Java nhưng detached. Việc sửa tiếp không được Hibernate tự lưu. Khi muốn giải phóng state sau khi đã ghi, thứ tự thông thường là:

~~~java
em.flush();  // SQL đã được gửi trong transaction.
em.clear();  // Giải phóng managed state của persistence context.
~~~

**Không dùng clear chỉ như một thủ thuật giải phóng RAM mà quên các thay đổi cần lưu.** Với một transaction lớn, flush+clear giúp giảm phần context đang giữ, nhưng transaction vẫn tồn tại và có thể giữ lock/trạng thái DB lâu.

### 5.3. Detach hoặc evict khi chỉ cần bỏ một entity

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
em.detach(order);

order.changeNote("không tự được ghi");
~~~

Đôi khi cần giữ những entity khác trong context nhưng không muốn quản lý một object đọc-only. **detach()** (JPA) hoặc **Session.evict()** (Hibernate) có thể hữu ích. Tuy nhiên các association/cascade detach và object graph đã được load cần được hiểu đúng; detaching parent không bảo đảm mọi object/collection liên quan cũng không còn managed.

### 5.4. Refresh để nạp dữ liệu DB mới

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
em.refresh(order); // Yêu cầu đọc lại state hiện tại từ DB.
~~~

**refresh()** khác clear: nó giữ đối tượng ở trạng thái managed và tải lại các giá trị theo mapping, có thể **ghi đè những thay đổi chưa lưu ở local**. Nó không tự vượt qua giới hạn của transaction isolation: trong một transaction REPEATABLE READ, snapshot DB có thể vẫn là snapshot cũ theo quy tắc database, kể cả khi refresh được gọi.

Khi chỉ cần giá trị cập nhật mới nhất sau một transaction khác, thường nên **kết thúc transaction/use case hiện tại rồi mở persistence context/transaction mới**, thay vì giữ Session từ rất lâu và refresh hàng trăm entity.

## 6. Quy tắc thực hành: transaction ngắn, mỗi batch một persistence context

Đối với import/migration/maintenance có lượng bản ghi lớn, chiến lược dễ kiểm soát là:

1. Đọc một batch có giới hạn bằng pagination/keyset.
2. Mở transaction xử lý batch đó.
3. Load/sửa entity cần thiết, commit batch.
4. Để persistence context của batch kết thúc.
5. Tiếp tục batch kế tiếp bằng một transaction mới.

~~~mermaid
flowchart TD
    A[Start job] --> B[Lấy batch đầu theo ID]
    B --> C{Có bản ghi?}
    C -->|Không| H[Hoàn thành job]
    C -->|Có| D[Transaction: xử lý batch]
    D --> E[Flush / commit]
    E --> F[Đóng persistence context batch]
    F --> G[Lưu checkpoint lastId]
    G --> B
~~~

Ưu điểm:

- Số entity managed tại một thời điểm được giới hạn gần với kích thước batch (trừ quan hệ lazy/fetch và tham chiếu khác).
- Mỗi transaction nhỏ hơn, lock/rollback thường dễ quản lý hơn.
- Có checkpoint để tiếp tục job nếu một batch lỗi.
- Hạn chế việc một Session được giữ mở trong suốt hàng giờ.

**Đổi lại:** job không còn một transaction nguyên tử cho tất cả bản ghi. Các batch trước đã commit không tự rollback khi batch sau lỗi. Muốn có tính nhất quán giữa các batch, cần checkpoint, idempotency, retry và workflow phù hợp.

### 6.1. Repository đọc theo keyset ID

~~~java
package com.example.shop.persistence;

import com.example.shop.domain.PurchaseOrder;
import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByIdGreaterThanOrderByIdAsc(
        Long lastId,
        Pageable pageable
    );
}
~~~

Truy vấn theo **id > lastId ORDER BY id** giúp tránh OFFSET ngày càng lớn, và không phụ thuộc việc ID liền nhau. Cần có khóa duy nhất/ổn định cho thứ tự. Nếu business data còn thay đổi đồng thời, phải định nghĩa điều kiện chọn tập xử lý (ví dụ thời điểm cutoff hoặc trạng thái) rõ ràng; keyset chỉ giải quyết một phần bài toán pagination.

### 6.2. Service xử lý đúng một batch

~~~java
package com.example.shop.application;

import com.example.shop.domain.PurchaseOrder;
import com.example.shop.persistence.PurchaseOrderRepository;
import java.util.List;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderBatchWorker {
    private final PurchaseOrderRepository orders;

    public OrderBatchWorker(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public BatchResult processAfter(Long lastId, int batchSize) {
        if (batchSize < 1 || batchSize > 1_000) {
            throw new IllegalArgumentException("batchSize phải trong khoảng 1..1000");
        }

        List<PurchaseOrder> batch =
            orders.findByIdGreaterThanOrderByIdAsc(
                lastId, PageRequest.of(0, batchSize));

        for (PurchaseOrder order : batch) {
            order.normalizeStatus();
        }

        Long nextId = batch.isEmpty()
            ? lastId
            : batch.get(batch.size() - 1).getId();

        return new BatchResult(batch.size(), nextId);
        // Transaction commit sau khi method kết thúc thành công.
    }

    public record BatchResult(int count, Long lastId) {}
}
~~~

Ví dụ trên giả định **PurchaseOrder.normalizeStatus()** là business method có kiểm tra phù hợp và thao tác này có thể lặp lại an toàn. Mỗi batch load tối đa batchSize entity root; nếu normalizeStatus đụng các collection lớn hoặc một association graph, cần tiếp tục giới hạn fetch plan.

### 6.3. Orchestrator bên ngoài transaction

~~~java
package com.example.shop.application;

import org.springframework.stereotype.Component;

@Component
public class OrderMaintenanceJob {
    private final OrderBatchWorker worker;

    public OrderMaintenanceJob(OrderBatchWorker worker) {
        this.worker = worker;
    }

    public void run() {
        Long lastId = 0L;
        while (true) {
            OrderBatchWorker.BatchResult result =
                worker.processAfter(lastId, 200);

            if (result.count() == 0) {
                break;
            }

            lastId = result.lastId();
            // Ghi checkpoint bền vững nếu job cần resume.
        }
    }
}
~~~

**Tại sao tách thành hai Spring bean?** Vì **@Transactional** kiểu proxy trong Spring chỉ áp dụng khi lời gọi đi qua proxy. Nếu một method trong cùng class gọi trực tiếp method khác của chính mình (self-invocation), annotation transaction ở method được gọi có thể không được áp dụng như tưởng tượng.

Ở cấu trúc trên, **OrderMaintenanceJob.run()** không mở một transaction lớn; mỗi lời gọi đến **OrderBatchWorker.processAfter()** qua bean Spring có transaction riêng và kết thúc sau batch. Với cấu hình transaction manager thông thường, transaction-bound EntityManager/Session của batch được giải phóng sau khi transaction kết thúc.

Không đặt **@Transactional** ở run() nếu mục tiêu là mỗi batch một transaction: transaction bao ngoài sẽ làm mất ranh giới ngắn và có thể khiến các thao tác dùng cùng một context/transaction không như mong muốn.

### 6.4. Chọn batch size

Không có một con số tối ưu duy nhất. Batch 50–500 entity root thường là điểm khởi đầu để thực nghiệm, nhưng nếu mỗi root có nhiều relation, giá trị thấp hơn có thể cần thiết; với thao tác rất đơn giản có thể tăng. Hãy đo:

- Heap còn lại sau mỗi batch và sau GC.
- Số SQL, row và độ trễ.
- Thời gian commit/flush.
- Lock, network và connection pool.
- Kích thước entity graph thực tế, không chỉ kích thước List root.

Đừng tăng batchSize chỉ vì việc gọi repository ít lần hơn. Batch quá lớn có thể làm context và transaction lại phình to.

## 7. Flush + clear theo lô trong một transaction: khi nào có ích?

Đôi khi một nghiệp vụ bắt buộc xử lý theo một transaction, hoặc framework đã giao cho bạn một Session cố định. Khi đó có thể **flush rồi clear định kỳ**:

~~~java
@Transactional
public void importWithinOneTransaction(List<OrderInput> source) {
    int count = 0;

    for (OrderInput input : source) {
        PurchaseOrder order = PurchaseOrder.from(input);
        entityManager.persist(order);

        if (++count % 100 == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
~~~

Ví dụ giả định **OrderInput**, **PurchaseOrder.from(input)** và **entityManager** đã được định nghĩa trong ứng dụng. Đây là cấu trúc minh họa, không phải code chạy độc lập. Khi dataset rất lớn, **source** bản thân cũng không nên là một List chứa toàn bộ dữ liệu; cần nguồn đọc theo từng phần.

**Ưu điểm:** context không giữ tất cả entity đã xử lý. **Hạn chế:**

- Toàn bộ vòng lặp vẫn nằm trong một transaction; lock, WAL/undo và chi phí rollback vẫn có thể lớn.
- Sau clear, những object trước đó là detached; sửa tiếp không tự lưu.
- Nếu các phần sau của nghiệp vụ cần tham chiếu entity trước đó như managed, phải load lại/thiết kế khác.
- Kích thước object graph và ActionQueue trong từng đoạn vẫn cần theo dõi.
- Với các lệnh phụ thuộc ID/quan hệ, phải hiểu thứ tự persist/flush và constraint.

Đối với import dài hàng giờ, **transaction theo batch riêng** thường là thiết kế bền vững hơn. Dùng flush+clear trong một transaction chỉ khi có yêu cầu nguyên tử rõ ràng và chi phí transaction được chấp nhận.

### 7.1. JDBC batching là vấn đề khác

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          batch_size: 50
        order_inserts: true
        order_updates: true
~~~

**hibernate.jdbc.batch_size** giúp gộp các statement JDBC tương thích khi Hibernate flush, giảm round-trip trong một số trường hợp. Nó **không giới hạn số entity managed trong persistence context**. Với IDENTITY ID generation, batch insert có thể bị hạn chế vì Hibernate cần lấy ID ngay.

Ba khái niệm phải tách bạch:

- **Page/batch xử lý:** giới hạn số bản ghi ứng dụng xử lý trong một lần.
- **JDBC batch:** gộp SQL tương thích để gửi hiệu quả.
- **flush + clear:** đồng bộ rồi dọn managed state.

Chúng có thể phối hợp, nhưng không thay thế nhau.

## 8. Khi chỉ cần đọc dữ liệu: projection, read-only và streaming

Nếu job xuất báo cáo CSV/JSON mà **không sửa entity**, không nhất thiết tải từng PurchaseOrder managed.

### 8.1. DTO projection làm giảm managed state

~~~java
public record OrderExportRow(Long id, Long customerId, String status) {}
~~~

~~~java
@Query("""
    select new com.example.shop.application.OrderExportRow(
        o.id, o.customerId, o.status
    )
    from PurchaseOrder o
    where o.id > :afterId
    order by o.id
    """)
List<OrderExportRow> findExportRowsAfter(
    @Param("afterId") Long afterId,
    Pageable pageable
);
~~~

Đoạn này minh họa query method trong repository, với mapping PurchaseOrder có các field **id**, **customerId**, **status** tương ứng (nếu entity thực tế có quan hệ Customer thì truy vấn nên dùng **o.customer.id** thay vì o.customerId). DTO projection tránh biến mỗi hàng thành một managed PurchaseOrder, thường tiết kiệm bộ nhớ và chi phí dirty checking.

Kết hợp DTO với keyset/page để giới hạn kích thước List được tạo trong memory. Dù là DTO, **một List hàng triệu phần tử vẫn có thể gây OutOfMemoryError**.

### 8.2. Đọc entity read-only

Spring:

~~~java
@Transactional(readOnly = true)
public List<PurchaseOrder> findRecent() {
    return repository.findTop100ByOrderByIdDesc();
}
~~~

**readOnly = true** là hint và chính sách transaction; Hibernate/Spring có thể tối ưu flush mode, read-only entity state tùy cấu hình. Nó **không biến một Session sống lâu thành Session có eviction tự động** và cũng không ngăn mọi kiểu ghi trong mọi database. Entity load vào persistence context vẫn có thể bị giữ đến khi context kết thúc.

Hibernate còn có **Session.setDefaultReadOnly(true)** và query read-only hints cho một số use case; trong read-only mode, Hibernate có thể giảm hoặc bỏ việc lưu snapshot phục vụ dirty checking cho entity tương ứng. Nhưng cần hiểu rõ đối tượng nào đã load trước khi thay đổi flag và việc cập nhật entity read-only không được đồng bộ theo cách nào. Với báo cáo thuần đọc, **DTO projection + batch** vẫn thường đơn giản hơn.

### 8.3. Stream/scroll không tự giải quyết cache tăng

Hibernate và Spring Data JPA hỗ trợ một số cách đọc kết quả theo stream/cursor:

~~~java
@Query("select o from PurchaseOrder o order by o.id")
Stream<PurchaseOrder> streamAll();
~~~

Và cần đóng stream khi dùng:

~~~java
@Transactional(readOnly = true)
public void export() {
    try (Stream<PurchaseOrder> stream = repository.streamAll()) {
        stream.forEach(this::writeRow);
    }
}
~~~

Ví dụ giả định lớp có **repository** và method **writeRow**. Stream phải được tiêu thụ khi transaction/EntityManager còn mở và được đóng; JDBC driver có thể giữ cursor/connection trong thời gian đọc. Khả năng server-side streaming phụ thuộc driver, fetch size, auto-commit và cấu hình.

Quan trọng: **Stream<ENTITY> vẫn có thể đưa các entity vào persistence context**. Nếu stream kéo dài qua hàng trăm nghìn hàng mà không quản lý state, memory vẫn có thể tăng. Vì thế với dữ liệu lớn cần cân nhắc:

- Stream **DTO/scalar** thay vì entity nếu chỉ xuất dữ liệu.
- Đọc từng trang với keyset rồi để transaction/context kết thúc sau trang.
- Streaming qua API nâng cao có kiểm soát fetch size và giải phóng state.
- Dùng **StatelessSession** cho thao tác độc lập phù hợp khi không cần persistence context.

Tránh mở stream rồi trả nó ra HTTP controller khi transaction đã kết thúc: lazy loading/cursor có thể lỗi; giữ transaction mở suốt một HTTP download lớn cũng cần đánh giá lock, timeout và tải hệ thống.

## 9. StatelessSession: một lựa chọn nâng cao cho batch

Hibernate cung cấp **StatelessSession**, khác với Session thông thường:

| Đặc tính | Session thường | StatelessSession |
|---|---|---|
| First-level cache / identity map | Có | Không theo mô hình stateful |
| Dirty checking tự động | Có đối với entity managed | Không theo cơ chế stateful thông thường |
| Thay đổi field tự flush | Có thể, theo transaction/flush | Không; phải gọi thao tác explicit |
| Cascade entity graph như Session thường | Có theo mapping | Không theo hành vi cascade truyền thống của stateful Session |
| Collection wrapper/persistent graph | Có | Không quản lý collection theo cách stateful |
| Dùng cho business aggregate phong phú | Thích hợp | Cần cẩn trọng |
| Dùng để xử lý khối lượng lớn với thao tác rõ ràng | Có, nhưng phải quản lý context | Có thể phù hợp |

Ví dụ ý tưởng:

~~~java
try (var session = sessionFactory.openStatelessSession()) {
    var tx = session.beginTransaction();
    try {
        PurchaseOrder order = session.get(PurchaseOrder.class, orderId);
        order.normalizeStatus();
        session.update(order); // Explicit, không dựa vào dirty checking.
        tx.commit();
    } catch (RuntimeException ex) {
        tx.rollback();
        throw ex;
    }
}
~~~

Đây là ví dụ API Hibernate, không phải JPA portable. Cách session tương tác với SQL, batching, lifecycle, cache và các tính năng nâng cao có thể khác giữa phiên bản Hibernate, nên cần xem tài liệu đúng version và thử nghiệm trước khi áp dụng hàng loạt.

StatelessSession **không phù hợp để thay Session thường vô điều kiện**:

- Logic cascade/orphan removal và collection thay đổi không hoạt động như managed graph.
- Cùng một row được đọc hai lần có thể cho ra các object độc lập, không có identity guarantee của persistence context.
- Business method dựa vào lazy associations hoặc entity lifecycle callbacks phải được thiết kế lại.
- Nếu có optimistic locking, cần hiểu cơ chế version trên các thao tác explicit.

Nó hữu ích khi job xử lý từng bản ghi độc lập, SQL/action rõ và cần tránh tích lũy persistence context.

## 10. Dữ liệu bị cũ: hai Session, một hàng

Giả sử database ban đầu có:

~~~text
purchase_orders:
id = 51
status = DRAFT
version = 0
~~~

Diễn biến:

~~~mermaid
sequenceDiagram
    participant A as Session A
    participant DB as Database
    participant B as Session B
    A->>DB: SELECT order #51
    DB-->>A: status=DRAFT, version=0
    Note over A: Order #51 được giữ managed
    B->>DB: SELECT order #51
    DB-->>B: status=DRAFT
    B->>DB: UPDATE status=CONFIRMED, version=1
    B->>DB: COMMIT
    Note over DB: Database hiện là CONFIRMED
    A->>A: find(Order, 51) lần nữa
    Note over A: Có thể dùng managed object cũ DRAFT
    A->>DB: refresh hoặc transaction/context mới
    DB-->>A: CONFIRMED theo isolation phù hợp
~~~

Session A có thể vẫn trả **DRAFT** vì object Order #51 đã nằm trong persistence context của nó. First-level cache được ưu tiên cho các lời gọi như **find()**, nhằm giữ identity và state nhất quán trong unit of work.

### 10.1. Query lại không có nghĩa lúc nào cũng làm mới entity

Một câu JPQL:

~~~java
List<PurchaseOrder> result = em.createQuery(
    "select o from PurchaseOrder o where o.id = :id",
    PurchaseOrder.class
).setParameter("id", 51L).getResultList();
~~~

có thể gửi SELECT xuống database, nhưng entity có ID ấy **đã managed** có thể được tái sử dụng mà không hydrate đè toàn bộ field đã giữ. Kết quả phụ thuộc query, flush mode và trạng thái context; đừng suy luận “có SQL SELECT trong log là object đã có giá trị mới nhất”.

Đó là đặc điểm quan trọng khi lập trình viên giữ một EntityManager qua nhiều request hoặc transaction.

### 10.2. Hai nguyên nhân stale khác nhau

| Nguyên nhân | Ví dụ | Hướng xử lý |
|---|---|---|
| **State cũ trong persistence context** | find lần hai trả instance Order đã nạp trước đó | Kết thúc context, clear/detach rồi load lại, hoặc refresh phù hợp |
| **Transaction isolation giữ snapshot DB cũ** | Transaction REPEATABLE READ không thấy commit mới của transaction khác | Kết thúc transaction/đổi ranh giới hoặc xem lại isolation policy |

Ngay cả khi clear persistence context, transaction đang chạy dưới REPEATABLE READ có thể tiếp tục thấy snapshot DB cũ. Ngược lại, ở READ COMMITTED, query mới có thể nhìn thấy dữ liệu commit gần nhất **ở cấp statement**, nhưng persistence context vẫn có thể trả object đã managed. Hai lớp này không được nhầm lẫn.

**Một Session mới không bảo đảm “dữ liệu thời gian thực tuyệt đối”** nếu hệ thống có replica lag, cache cấp hai stale do nguồn ghi ngoài hệ thống, transaction isolation khác hoặc dữ liệu lại thay đổi ngay sau khi đọc. Cần xác định yêu cầu nhất quán của use case.

## 11. Ba cách ứng phó stale state: scope mới, refresh, clear

### 11.1. Ưu tiên ranh giới unit of work ngắn

Với các API thông thường, cách đơn giản nhất để tránh stale state lâu ngày là **không giữ Session lâu ngày**. Mỗi use case bắt đầu transaction, đọc dữ liệu cần thiết, xử lý/ghi, rồi đóng transaction và để context kết thúc.

~~~java
@Service
public class OrderQueryService {
    private final PurchaseOrderRepository repository;

    public OrderQueryService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public OrderStatus getStatus(Long id) {
        PurchaseOrder order = repository.findById(id)
            .orElseThrow(() -> new IllegalArgumentException("Không có đơn"));
        return order.getStatus();
    }
}
~~~

Ví dụ này trả một enum/DTO ra ngoài transaction, không trả nguyên managed entity. Khi request mới dùng transaction-bound persistence context mới, nó không tái sử dụng entity managed từ request trước theo cơ chế first-level cache.

### 11.2. Refresh khi thật sự cần đọc lại một entity

~~~java
@Transactional
public OrderStatus reloadStatus(Long id) {
    PurchaseOrder order = em.find(PurchaseOrder.class, id);
    em.refresh(order);
    return order.getStatus();
}
~~~

Điều kiện quan trọng:

- Entity phải ở trạng thái managed để refresh theo cách sử dụng thông thường.
- **refresh có thể ghi đè thay đổi local chưa lưu** của entity.
- Nó có thể gây thêm SQL và kéo theo trạng thái quan hệ theo quy tắc mapping/cascade.
- Không bảo đảm nhìn thấy commit khác nếu transaction isolation vẫn giữ snapshot cũ.

Đừng gọi refresh sau mọi find như một “cách tắt cache” toàn cục; việc ấy làm mất lợi ích identity map và tạo truy vấn thừa.

### 11.3. Clear để bắt đầu lại state trong cùng EntityManager

~~~java
PurchaseOrder old = em.find(PurchaseOrder.class, id);
em.clear();
PurchaseOrder reloaded = em.find(PurchaseOrder.class, id);

System.out.println(old == reloaded); // false đối với hai object khác nhau
~~~

Sau clear, old bị detached; reloaded được nạp thành managed instance mới. Nhưng trong transaction REPEATABLE READ, hai lần query vẫn có thể đọc snapshot SQL cũ. Và nếu code còn dùng biến **old** sau clear, nó vẫn chứa dữ liệu cũ trong bộ nhớ.

Việc **em.clear()** ảnh hưởng **tất cả** entity managed trong context, nên có thể làm các phần khác của use case mất dirty tracking. Với chỉ một entity cần bỏ, dùng detach; với nhiều thao tác ghi chưa flush, xử lý pending changes trước khi clear.

## 12. Optimistic locking bảo vệ ghi đè, không tự làm mới dữ liệu đọc

Một trong những nguy hiểm của Session tồn tại lâu là **ghi đè state mới bằng dữ liệu cũ** (*lost update*). Ví dụ Session A đọc DRAFT, Session B xác nhận đơn thành CONFIRMED, sau đó Session A thay đổi ghi chú rồi flush cả state của Order. Nếu mapping/update phù hợp, A có nguy cơ cập nhật dựa trên dữ liệu đã lỗi thời.

Thêm version:

~~~java
@Entity
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    private String note;

    @Version
    private long version;

    protected PurchaseOrder() {}

    public void changeNote(String newNote) {
        this.note = newNote;
    }
}
~~~

Hibernate có thể tạo câu cập nhật tương tự:

~~~sql
UPDATE purchase_orders
SET note = ?, version = ?
WHERE id = ? AND version = ?;
~~~

Nếu Session B đã commit khiến version đổi từ 0 lên 1, Session A cập nhật với **WHERE version = 0** không còn khớp row, và Hibernate báo lỗi optimistic locking. Ứng dụng xử lý bằng cách thông báo xung đột hoặc **đọc lại state trong transaction mới và retry use case sau khi kiểm tra quy tắc nghiệp vụ**.

### 12.1. Version không phải cơ chế refresh

Session A có thể tiếp tục **hiển thị DRAFT cũ** cho đến khi re-read/refresh, ngay cả khi dùng @Version. Version chủ yếu ngăn cập nhật dựa trên version cũ được commit một cách âm thầm; nó **không tự đẩy thay đổi từ DB vào mọi Session**.

### 12.2. Bulk JPQL/native SQL có thể bỏ qua @Version

~~~java
int changed = em.createQuery("""
    update PurchaseOrder o
    set o.status = :status
    where o.id = :id
    """)
    .setParameter("status", OrderStatus.CONFIRMED)
    .setParameter("id", orderId)
    .executeUpdate();
~~~

JPQL bulk update thường thao tác trực tiếp trên DB, **không đồng bộ state của các entity managed** đang có trong persistence context, và không tự động áp dụng cùng một cơ chế version/lifecycle event như dirty checking entity. Nếu use case yêu cầu version, phải có thiết kế query/điều kiện version phù hợp hoặc dùng entity-managed update.

Sau bulk update, entity **đã load trước đó** có thể vẫn cũ. Đừng tưởng SQL ảnh hưởng một row thì object managed tương ứng tự đổi field.

## 13. Bulk update, native query và stale persistence context

Một tình huống rất thường gặp:

~~~java
@Transactional
public void markConfirmed(Long orderId) {
    PurchaseOrder loaded = em.find(PurchaseOrder.class, orderId);

    em.createQuery("""
        update PurchaseOrder o
        set o.status = :status
        where o.id = :id
        """)
        .setParameter("status", OrderStatus.CONFIRMED)
        .setParameter("id", orderId)
        .executeUpdate();

    // loaded.getStatus() có thể vẫn là giá trị trước bulk UPDATE.
}
~~~

Hướng giải quyết tùy use case:

1. **Không dùng bulk update** nếu chỉ sửa một managed entity; gọi business method rồi để dirty checking flush.
2. Sau bulk update, **clear()** khi không có pending managed changes cần giữ, rồi nạp lại.
3. **refresh(entity)** nếu cần đồng bộ một entity cụ thể và mapping/isolation phù hợp.
4. Với tác vụ bulk rộng, thực hiện DML trong **transaction/persistence context riêng**, đừng đồng thời giữ một graph managed lớn đang sửa.

Trong Spring Data JPA:

~~~java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query("""
    update PurchaseOrder o
    set o.status = :status
    where o.id = :id
    """)
int bulkChangeStatus(@Param("id") Long id,
                     @Param("status") OrderStatus status);
~~~

**flushAutomatically = true** yêu cầu flush trước khi chạy query; **clearAutomatically = true** yêu cầu clear context sau đó. Đây là công cụ có ích nhưng không nên bật máy móc: flush các thay đổi khác có thể phát sinh SQL sớm, còn clear detach toàn bộ entity trong context, làm các thao tác Java sau đó không còn được quản lý tự động.

Với native SQL từ một tiến trình khác, tình trạng tương tự xảy ra: database thay đổi nhưng Session hiện hữu không biết state cần cập nhật. Database trigger có thể sửa cột sau INSERT/UPDATE; Hibernate cần mapping generated phù hợp hoặc refresh để phản ánh giá trị đó.

## 14. Open Session in View: kéo dài scope qua tầng web

Trong ứng dụng web, **Open Session in View (OSIV)** hoặc **Open EntityManager in View** giữ EntityManager/Session mở trong quá trình xử lý request và render view/serialize response. Một lợi ích là controller/view có thể truy cập lazy association sau khi service transaction kết thúc.

Nhưng OSIV có trade-off:

- Persistence context tồn tại lâu hơn phạm vi service transaction.
- JSON serialization có thể vô tình khởi tạo nhiều quan hệ lazy, gây N+1.
- Code tầng web có thể trở thành nơi phát sinh SQL không được đo/kiểm soát tại service.
- Khi xử lý view/response lâu, Session tồn tại lâu; chi phí connection phụ thuộc cách cấp/giữ connection và transaction, **không tự mặc định giữ một JDBC connection từ đầu đến cuối request**.
- Nếu trong cùng request có nhiều transaction hoặc thao tác DB bên ngoài, các entity đã managed có thể không tự phản ánh thay đổi.

Với Spring Boot, có thể chọn chính sách rõ ràng:

~~~yaml
spring:
  jpa:
    open-in-view: false
~~~

Khi tắt OSIV, hãy tạo response DTO trong **service @Transactional** và fetch đúng dữ liệu cần thiết:

~~~java
@Transactional(readOnly = true)
public OrderDetailView getDetail(Long id) {
    PurchaseOrder order = repository.findDetailById(id)
        .orElseThrow(() -> new IllegalArgumentException("Không có đơn"));
    return new OrderDetailView(
        order.getId(),
        order.getStatus(),
        order.getItems().stream()
            .map(i -> new ItemView(i.getId(), i.getQuantity()))
            .toList()
    );
}
~~~

Đoạn trên giả định **OrderDetailView**, **ItemView**, **findDetailById** và association **items** đã được định nghĩa phù hợp. Mục tiêu là giải thích ranh giới đọc dữ liệu; không phải bật EAGER cho toàn bộ association.

**OSIV không phải nguyên nhân duy nhất của long Session.** Session còn có thể bị giữ lâu vì:

- EntityManager được tạo thủ công rồi không close.
- Conversation-scoped/extended persistence context.
- @Transactional bao một tác vụ background rất dài.
- Tầng ứng dụng cất EntityManager hoặc entity graph managed vào field singleton.
- Stream/cursor chưa đóng.

Chỉ tắt OSIV mà vẫn giữ EntityManager thủ công trong hàng giờ thì vấn đề chưa được giải quyết.

## 15. Session không thread-safe và không nên giữ trong singleton

**Hibernate Session/EntityManager không được thiết kế để dùng đồng thời từ nhiều thread.** SessionFactory/EntityManagerFactory có thể được chia sẻ; Session thông thường thì không.

Ví dụ sai:

~~~java
@Component
public class UnsafeSessionHolder {
    private final Session session;

    public UnsafeSessionHolder(SessionFactory factory) {
        this.session = factory.openSession();
    }

    public PurchaseOrder load(Long id) {
        return session.get(PurchaseOrder.class, id);
    }
}
~~~

Nếu đây là Spring singleton, mọi request gọi cùng Session. Hệ quả có thể là:

- Race condition trên persistence context không thread-safe.
- Entity managed tích lũy qua nhiều request.
- Dữ liệu cũ được tái sử dụng.
- Quản lý transaction/connection lẫn lộn và khả năng rò rỉ Session.

Thiết kế đúng thường inject **EntityManager** theo cơ chế Spring/JPA để framework cung cấp proxy gắn vào transaction/request context thích hợp, hoặc mở Session trong một scope rõ rồi đóng:

~~~java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();
    try {
        PurchaseOrder order = session.get(PurchaseOrder.class, orderId);
        // Xử lý ngắn trong transaction.
        tx.commit();
    } catch (RuntimeException ex) {
        tx.rollback();
        throw ex;
    }
}
~~~

Ví dụ trên dùng API Hibernate trực tiếp; với Spring Boot, **@Transactional** và dependency injection thường tiện và an toàn hơn cho service thông thường. Nếu dùng async hoặc thread pool, mỗi task cần transaction/context riêng, **không truyền Session đang mở cho thread khác**.

## 16. Extended persistence context: có lý do tồn tại nhưng phải quản lý

JPA hỗ trợ **extended persistence context** trong một số môi trường ứng dụng stateful, tồn tại qua nhiều transaction và gắn với một cuộc hội thoại nghiệp vụ (*conversation*). Mục tiêu có thể là cho người dùng chỉnh một graph qua nhiều bước trước khi commit.

Đây là lựa chọn có chủ đích, không phải pattern mặc định cho REST API stateless.

Rủi ro khi conversation kéo dài:

- Entity đã load tiếp tục managed qua thời gian dài.
- Memory tăng nếu mỗi bước nạp thêm dữ liệu.
- Dữ liệu bên ngoài thay đổi có thể không hiện trong graph đang giữ.
- Khi commit cuối, conflict version hoặc constraint phát hiện muộn.
- Cần quản lý thời hạn conversation, rollback/hủy thao tác và giới hạn số entity.

Đối với workflow nhiều bước như checkout, nhiều hệ thống sẽ lưu **DTO/draft state** (hoặc bản ghi nháp riêng) thay vì giữ một Session và graph managed từ lần HTTP đầu tới cuối. Mỗi bước đọc/ghi qua transaction ngắn, dùng **@Version** và quy tắc kiểm tra trước khi xác nhận.

Nếu dùng extended context thật sự, cần xác định chiến lược refresh/merge, conflict resolution và memory budget, không coi nó là “Session được phép tồn tại mãi”.

## 17. Monitoring: nhận biết memory leak hay chỉ là working set lớn

Đừng đoán chỉ bằng thông báo “heap tăng”. Một batch xử lý có thể tạo nhiều object tạm rồi giải phóng bình thường sau GC. Một Session giữ managed object mới gây vấn đề kéo dài khi object không còn cần thiết nhưng vẫn được giữ bởi context.

### 17.1. Các tín hiệu cần theo dõi

| Tín hiệu | Câu hỏi cần trả lời |
|---|---|
| Used heap sau full GC hoặc sau các batch | Working set có tiếp tục tăng hay ổn định? |
| GC pause/time và allocation rate | Có áp lực tạo/giữ object quá mức? |
| Số entity load trong Hibernate Statistics | Mỗi batch tạo bao nhiêu entity managed? |
| Thời gian flush/commit | Có tăng theo tổng số entity đã xử lý trong một context? |
| Prepared statement count | Có N+1 hoặc quá nhiều query theo ID? |
| Số row đọc và fetch size | Dữ liệu có được giới hạn từng phần? |
| DB transaction age, lock waits | Transaction dài có giữ tài nguyên DB? |
| Connection pool active/awaiting | Có tình trạng giữ connection/cursor quá lâu? |

Không suy luận “session giữ entity N” chỉ từ **getEntityLoadCount()**: Statistics là counter tích lũy, không phải số entity đang managed tại một thời điểm. Nó giúp xác định khối lượng load, nhưng để hiểu retaining references cần quan sát heap, session scope và object graph.

### 17.2. Hibernate Statistics

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        generate_statistics: true

logging:
  level:
    org.hibernate.SQL: DEBUG
~~~

Đọc thống kê:

~~~java
import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory sessionFactory = emf.unwrap(SessionFactory.class);
Statistics stats = sessionFactory.getStatistics();

long loads = stats.getEntityLoadCount();
long statements = stats.getPrepareStatementCount();
long flushes = stats.getFlushCount();
long updates = stats.getEntityUpdateCount();
~~~

Ví dụ trên giả định **emf** là EntityManagerFactory đã có sẵn. Bộ đếm thuộc **SessionFactory**, cộng dồn từ lúc bắt đầu hoặc clear thống kê; nhiều request/batch có thể cùng tăng chúng. Chúng không tự trả lời “heap bị ai giữ” hoặc “row nào đang stale”.

Trong môi trường test cô lập, có thể so sánh số liệu trước/sau một batch. Không nên gọi **Statistics.clear()** từ một request production vì nó reset số liệu chung của ứng dụng.

### 17.3. SQL log và heap inspection

Ở local với Hibernate 6:

~~~yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

Logger bind có thể chứa thông tin cá nhân, nên chỉ bật theo chính sách bảo mật và trong thời gian phù hợp. SQL log giúp nhìn:

- Có hàng trăm nghìn **SELECT by ID** thay vì query theo batch không?
- Có N+1 từ việc load OrderItem/Product?
- Khi flush cuối job, có rất nhiều UPDATE/INSERT chờ thực thi?
- Đọc lại Order bằng find() có phát SQL hay lấy object đã managed?

Đối với memory, có thể dùng Java Flight Recorder, VisualVM, heap histogram hoặc heap dump trong môi trường có quyền phù hợp để tìm retained object và đường tham chiếu. Heap dump có thể chứa dữ liệu nhạy cảm của người dùng; phải quản lý truy cập và lưu trữ cẩn thận. **Không tự gắn nhãn memory leak** nếu heap tăng tạm thời nhưng sau GC trở về mức ổn định.

## 18. Kiểm thử tình huống dữ liệu cũ và bộ nhớ tăng

### 18.1. Thử nghiệm identity map trong một context

~~~java
@Transactional
public void showIdentity(Long id) {
    PurchaseOrder a = em.find(PurchaseOrder.class, id);
    PurchaseOrder b = em.find(PurchaseOrder.class, id);

    if (a != b) {
        throw new AssertionError("Cùng persistence context phải có identity nhất quán");
    }
}
~~~

Quan sát SQL log để thấy lần find thứ hai thường không cần SELECT nếu entity đã managed. Điều này chứng minh first-level cache hoạt động.

### 18.2. Thử nghiệm stale state với hai context

Tạo hai EntityManager riêng từ cùng EntityManagerFactory và chạy transaction rõ ràng:

1. **EM A**: bắt đầu transaction, đọc Order #51 là DRAFT.
2. **EM B**: trong transaction khác, chuyển Order #51 sang CONFIRMED và commit.
3. **EM A**: đọc lại bằng **find()** và so sánh object/state đang managed.
4. **EM A**: thử **refresh()** rồi quan sát state theo isolation level hiện tại.
5. Kết thúc transaction/context A, mở **EM C** mới và đọc Order #51.

Nếu dùng PostgreSQL READ COMMITTED, refresh hoặc context mới thường có cơ hội thấy commit của B khi bắt đầu statement mới; với REPEATABLE READ, transaction A vẫn có snapshot cũ. Cần thực sự cấu hình isolation mong muốn và tránh dựa trên transaction test tự rollback che kết quả.

### 18.3. Thử nghiệm bulk update

Trong cùng persistence context:

1. find Order #51, ghi lại status ở object Java.
2. Chạy JPQL bulk UPDATE để sửa status.
3. Đọc status từ object đã managed và từ SQL/database.
4. clear hoặc refresh phù hợp rồi quan sát lại.

Mục tiêu: chứng minh bulk DML không tự hydrate managed entity.

### 18.4. Thử nghiệm flush + clear trên batch

Tạo đủ dữ liệu đại diện, ví dụ 50.000 đơn hàng (không cần sinh dữ liệu trong bài đọc). Chạy hai biến thể trên schema test:

| Biến thể | Cách xử lý | Điều quan sát |
|---|---|---|
| A | Một transaction, load toàn bộ entity, commit cuối | Heap, số entity load, thời gian flush cuối |
| B | Batches 200 hoặc 500 entity, transaction riêng từng batch | Heap giữa batch, commit latency, tổng thời gian |
| C | Một transaction có flush+clear mỗi 200 entity | Heap giảm nhưng transaction/lock vẫn dài |
| D | DTO projection theo keyset để xuất báo cáo | Managed entity ít hơn; vẫn cần giới hạn DTO list |

Số liệu phải do người học đo, không dự đoán chính xác số megabyte hay số mili giây cho mọi hệ thống. Quan trọng là **đối chiếu cùng workload** và giải thích sự khác biệt từ vòng đời persistence context.

## 19. Những tình huống khó thường bị bỏ sót

### 19.1. Clear rồi vẫn OutOfMemoryError

Có thể code vẫn giữ List toàn bộ entity:

~~~java
List<PurchaseOrder> all = repository.findAll();
em.clear();
// all vẫn giữ các object Java, heap chưa được giải phóng.
~~~

**clear()** chỉ bỏ tham chiếu quản lý của Hibernate, không xóa các tham chiếu trong biến **all**. Phải đổi cách đọc theo page/stream DTO hoặc bỏ tham chiếu khỏi collection của ứng dụng.

### 19.2. Đọc theo trang nhưng một transaction vẫn giữ rất nhiều entity

~~~java
@Transactional
public void processPages() {
    for (int page = 0; page < 1_000; page++) {
        List<PurchaseOrder> chunk =
            repository.findAll(PageRequest.of(page, 200)).getContent();
        chunk.forEach(PurchaseOrder::normalizeStatus);
    }
}
~~~

Mỗi List có 200 row, nhưng **một transaction/persistence context** có thể giữ tất cả entity đã load. Ngoài ra OFFSET lớn có thể làm truy vấn ngày càng tốn kém và các thay đổi tập dữ liệu trong lúc paging có thể gây bỏ sót/lặp. Cần per-batch transaction hoặc flush+clear, và cân nhắc keyset.

### 19.3. Clear sau khi update một phần của graph

Nếu một Order managed có OrderItem chưa flush, clear đột ngột có thể làm mất thay đổi pending. Nếu một đoạn nghiệp vụ cần tiếp tục sửa chính graph ấy sau clear, object trở thành detached. Sửa **order** rồi mong Hibernate tự lưu lúc commit sẽ không còn hoạt động như trước.

**Nguyên tắc:** đặt clear ở ranh giới nơi đơn vị công việc đã hoàn chỉnh và được đồng bộ; không chen clear giữa các invariant cần kiểm tra trên cùng managed graph.

### 19.4. Batch có external API chậm

Không nên giữ transaction mở trong lúc gọi HTTP tới hệ thống khác hàng phút:

~~~java
@Transactional
public void synchronize(PurchaseOrder order) {
    externalApi.sendOrder(order); // Có thể timeout hoặc chậm.
    order.markSynchronized();
}
~~~

Cần cân nhắc pattern như outbox, queue, checkpoint/idempotency, hoặc tách bước đọc và ghi trạng thái thành transaction ngắn. Gọi API bên ngoài khi giữ lock/connection/transaction tăng rủi ro contention, và một transaction rollback không thể tự hoàn tác side effect HTTP đã gửi.

### 19.5. Retry lỗi optimistic lock trong cùng Session cũ

Sau optimistic locking failure, transaction thường đã không còn thích hợp để tiếp tục. Không nên sửa lại version hay retry bằng chính managed entity cũ trong cùng transaction. **Rollback, mở transaction/persistence context mới, đọc state hiện tại và quyết định retry toàn bộ use case** nếu nghiệp vụ cho phép.

### 19.6. Kéo dài read-only transaction để “giữ dữ liệu nhất quán”

Một read-only transaction dài có thể tránh một số hiện tượng thay đổi giữa các câu query tùy isolation level, nhưng cũng có thể giữ snapshot DB lâu, tăng áp lực MVCC/vacuum trong PostgreSQL và ảnh hưởng tài nguyên. Read-only không đồng nghĩa không có chi phí vận hành. Với báo cáo lớn, cần xác định snapshot consistency thật sự cần thiết và cách xuất dữ liệu phù hợp.

## 20. Bảng chẩn đoán nhanh

| Dấu hiệu | Khả năng nguyên nhân | Hướng giải quyết |
|---|---|---|
| Heap tăng đều trong một batch lớn | Persistence context giữ entity/snapshot/collection | Xử lý theo batch với context ngắn; flush+clear khi phù hợp |
| Heap không giảm dù em.clear() | List/Map/queue của ứng dụng còn tham chiếu object | Bỏ tham chiếu, đổi sang paging/DTO/stream giới hạn |
| Commit cuối job mất rất lâu | Dirty checking/action queue quá lớn, transaction dài | Batch transaction, giới hạn entity graph, xem SQL |
| find cùng ID không phát SELECT lần hai | First-level cache có object managed | Đúng semantics; mở context mới hoặc refresh nếu cần dữ liệu mới |
| SELECT đã chạy nhưng field entity vẫn cũ | Managed instance được tái sử dụng | Refresh/clear theo ranh giới; kiểm tra isolation |
| Clear rồi dữ liệu cập nhật không được lưu | Clear trước flush, entity thành detached | Flush trước clear, hoặc tránh clear giữa use case |
| Đọc lại vẫn cũ sau refresh | Transaction snapshot/replica lag hoặc nguồn dữ liệu khác | Xem isolation, transaction mới, đường đọc DB |
| Cập nhật bị OptimisticLockException | Version DB đã đổi, entity local cũ | Rollback, đọc lại ở transaction mới, xử lý conflict |
| Bulk update thành công nhưng Java giữ status cũ | Bulk DML bypass managed state | Flush/clear hoặc refresh phù hợp |
| Nhiều SQL khi serialize response | OSIV/lazy loading hoặc N+1 | Tạo DTO ở service, fetch plan phù hợp, cân nhắc tắt OSIV |
| Stream đọc lâu và giữ connection | Cursor/transaction chưa đóng | Đóng stream, dùng paging/transaction ngắn |
| Session hỏng khi request đồng thời | Dùng chung Session qua nhiều thread | Chỉ chia sẻ SessionFactory; mỗi task có context riêng |
| JDBC batch bật mà RAM vẫn tăng | JDBC batching không evict entity | Quản lý persistence context độc lập |
| @Transactional không có hiệu lực | Self-invocation hoặc bean không qua proxy | Tách service/worker bean hoặc dùng transaction management rõ ràng |

## 21. Bài thực hành cuối bài

Xây dựng một ứng dụng nhỏ Spring Boot + Hibernate + PostgreSQL với các bảng **customers**, **purchase_orders**, **order_items**, **products**. Thiết kế PurchaseOrder có **@Version**, **status**, **note** và quan hệ LAZY tới OrderItem. Thực hiện:

**Phần A — Bộ nhớ**

1. Tạo fixture vài chục nghìn đơn và dòng hàng ở database test.
2. Viết phiên bản xử lý một transaction với findAll(), ghi heap/SQL/flush time.
3. Viết phiên bản đọc 200 đơn mỗi batch, mỗi batch một transaction; dùng keyset theo ID.
4. Thử cùng một transaction nhưng flush+clear mỗi 200 entity, giải thích trade-off về lock/rollback.
5. Thay query full entity bằng DTO projection cho job chỉ xuất dữ liệu.
6. So sánh heap sau GC, transaction age và total execution time; không chỉ so statement count.

**Phần B — Dữ liệu bị cũ**

1. Mở EM A đọc Order #51.
2. Dùng EM B cập nhật, commit và đổi version.
3. Thử **find()** lại qua EM A, rồi thử **refresh()** và transaction mới.
4. Lặp phép thử với isolation READ COMMITTED và REPEATABLE READ nếu môi trường hỗ trợ.
5. Chạy bulk JPQL update trong context đã load Order, chứng minh entity managed có thể cũ.
6. Thử sửa Order cũ có @Version và quan sát optimistic locking conflict.

**Phần C — Ranh giới ứng dụng**

1. Tắt **spring.jpa.open-in-view**, viết service trả DTO chi tiết đơn.
2. Tạo job orchestrator và worker ở hai bean, xác nhận mỗi batch có transaction riêng.
3. Thử truy vấn bằng stream, bảo đảm transaction/cursor được đóng; quan sát vì sao streaming entity vẫn cần quản lý context.
4. Thảo luận cách tách external API call khỏi DB transaction bằng queue/outbox hoặc checkpoint.

Kết quả cần đạt là có thể chứng minh bằng SQL, dữ liệu DB, log và đo memory:

- **Entity managed không bị giải phóng chỉ vì biến local kết thúc.**
- **Flush không clear; clear không commit.**
- **Session lâu sống có thể giữ state cũ dù DB đã được transaction khác cập nhật.**
- **@Version ngăn lost update nhưng không biến Session thành nguồn dữ liệu luôn mới.**
- **Transaction/context ngắn và xử lý theo batch có giới hạn là mặc định an toàn cho tác vụ lớn.**

## 22. Nguyên tắc thiết kế cuối cùng

Một Session là **unit of work**, không phải nơi lưu lâu dài mọi object của ứng dụng. Hibernate giữ persistence context để bảo đảm identity, lazy loading và dirty checking **trong một phạm vi hữu ích**; khi phạm vi đó không có điểm kết thúc rõ ràng, hai rủi ro xuất hiện:

1. **Bộ nhớ tăng:** context tiếp tục tham chiếu entity, snapshot, collection, proxy và pending action. Cách xử lý là giới hạn khối lượng công việc, kết thúc transaction/context, hoặc flush+clear/detach khi có chủ đích.
2. **Dữ liệu bị cũ:** context tiếp tục trả managed instance đã load trước đó. Cách xử lý là đặt ranh giới transaction/persistence context phù hợp, sử dụng refresh/clear khi thật sự cần, và bảo vệ cập nhật đồng thời bằng version/locking theo nghiệp vụ.

Đừng sửa triệu chứng bằng cách tùy tiện tăng heap, bật JDBC batch hoặc gọi refresh ở mọi nơi. Hãy bắt đầu từ câu hỏi: **Session này do ai tạo, quản lý bao nhiêu entity, kết thúc ở đâu, và dữ liệu trong nó cần mới đến mức nào?**

Khi trả lời rõ những câu hỏi đó, bạn có thể sử dụng Hibernate ORM hiệu quả cả trong HTTP request nhỏ lẫn job xử lý hàng triệu bản ghi, đồng thời giữ nhất quán dữ liệu mà không biến persistence context thành một kho state lâu sống khó kiểm soát.

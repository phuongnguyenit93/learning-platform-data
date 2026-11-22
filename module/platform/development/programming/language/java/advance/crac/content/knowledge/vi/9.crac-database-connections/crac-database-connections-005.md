# EntityManager, Hibernate Session và tài nguyên truy cập dữ liệu

Trong một ứng dụng Java dùng JPA hoặc Hibernate, việc truy cập cơ sở dữ liệu không chỉ phụ thuộc vào một đối tượng kết nối. Một request có thể đi qua EntityManager, Hibernate Session, persistence context, transaction manager, JDBC connection, connection pool, statement, result set và cache. Một số đối tượng sống trong phạm vi một transaction; một số khác sống suốt vòng đời ứng dụng. Khi dùng CRaC (Coordinated Restore at Checkpoint), cần phân biệt các vòng đời này để biết thành phần nào có thể giữ lại, thành phần nào phải kết thúc trước checkpoint và thành phần nào cần được khởi tạo hoặc kiểm tra lại sau restore.

EntityManager và Hibernate Session thường đại diện cho một đơn vị làm việc truy cập dữ liệu. Chúng giữ persistence context, theo dõi entity được quản lý và phối hợp với transaction để đồng bộ thay đổi xuống database. Chúng thường ngắn hạn và không được chia sẻ tùy tiện giữa các thread. Trong khi đó, EntityManagerFactory và Hibernate SessionFactory là các factory dài hạn, dùng để tạo các đơn vị làm việc mới và thường được chia sẻ trong ứng dụng.

Khi checkpoint, một request hoặc transaction đang hoạt động có thể để lại trạng thái dở dang trong bộ nhớ và kết nối. Vì vậy, ứng dụng cần ngừng nhận công việc mới, hoàn tất hoặc rollback transaction đang chạy, đóng các EntityManager/Session do ứng dụng sở hữu và xử lý connection pool theo tích hợp được hỗ trợ. Sau restore, request mới cần tạo persistence context và transaction mới, đồng thời dùng kết nối hợp lệ.

## 1. EntityManager trong JPA

JPA (Jakarta Persistence, trước đây thường được gọi là Java Persistence API) định nghĩa một API tiêu chuẩn để ánh xạ đối tượng Java với dữ liệu quan hệ. EntityManager là giao diện chính để ứng dụng tương tác với persistence context.

Một EntityManager thường cung cấp các thao tác:

- Tìm entity theo khóa chính bằng find().
- Đưa entity mới vào persistence context bằng persist().
- Đánh dấu entity để xóa bằng remove().
- Đồng bộ trạng thái entity với database bằng flush().
- Tìm entity bằng JPQL, Criteria API hoặc native query.
- Làm mới hoặc tách entity khỏi persistence context bằng refresh() và detach().
- Đóng EntityManager do ứng dụng tự tạo bằng close().

EntityManager không đơn thuần là một wrapper quanh JDBC Connection. Nó quản lý một persistence context, theo dõi entity, quan hệ giữa entity, trạng thái dirty checking và cách đồng bộ các thay đổi với database. Khi ứng dụng gọi persist() hoặc sửa một entity đang được quản lý, câu lệnh SQL có thể chưa được gửi ngay. Provider thường giữ thay đổi trong bộ nhớ và thực hiện SQL khi flush hoặc tại một thời điểm thích hợp trong transaction.

Ví dụ:

```java
EntityManager em = entityManagerFactory.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Product product = new Product();
    product.setName("Keyboard");
    product.setPrice(45.00);

    em.persist(product);

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Ví dụ minh họa EntityManager do ứng dụng tự tạo và tự đóng. Trong ứng dụng dùng container hoặc Spring, EntityManager có thể được inject dưới dạng proxy và lifecycle thực tế do framework hoặc transaction manager quản lý. Khi đó, không được áp dụng máy móc đoạn code tự tạo/đóng này cho EntityManager được container quản lý.

## 2. Hibernate Session

Hibernate ORM là một persistence provider phổ biến triển khai JPA và cũng cung cấp API native của riêng mình. Hibernate Session là giao diện làm việc chính trong API native. Về mặt khái niệm, Session và EntityManager đảm nhiệm vai trò tương tự: đại diện cho một persistence context và một đơn vị làm việc với database.

Tùy phiên bản Hibernate và cách tích hợp, ứng dụng có thể làm việc qua EntityManager của JPA hoặc qua Session API. Khi dùng Hibernate làm JPA provider, EntityManager thường được triển khai dựa trên cơ chế Session của Hibernate. Tuy nhiên, cần tham khảo API của đúng phiên bản thay vì giả định mọi phiên bản có quan hệ kiểu hoặc hành vi giống hệt nhau.

Session cung cấp các thao tác native như:

- get() hoặc find() để tải entity.
- persist(), save() hoặc các API tương ứng để lưu entity, tùy phiên bản.
- remove()/delete() để xóa entity, tùy API.
- createQuery() để tạo HQL/JPQL hoặc query theo API Hibernate.
- flush() để đồng bộ persistence context với database.
- clear() để detach toàn bộ entity khỏi persistence context.
- close() để kết thúc Session.

Ví dụ dùng Session API:

```java
Session session = sessionFactory.openSession();
Transaction tx = null;

try {
    tx = session.beginTransaction();

    Product product = new Product();
    product.setName("Keyboard");
    product.setPrice(45.00);

    session.persist(product);

    tx.commit();
} catch (RuntimeException ex) {
    if (tx != null && tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    session.close();
}
```

Trong ví dụ, ứng dụng mở Session, bắt đầu transaction, thực hiện thay đổi rồi commit hoặc rollback và cuối cùng đóng Session. Cần dùng đúng API và kiểu transaction của phiên bản Hibernate trong dự án.

## 3. EntityManager và Session khác nhau ở đâu?

EntityManager là API chuẩn của Jakarta Persistence. Session là API native của Hibernate. Khi dùng Hibernate làm provider, cả hai thường dẫn đến cùng một cơ chế persistence context, nhưng Session có thể cung cấp thêm các khả năng riêng của Hibernate.

| Tiêu chí | JPA EntityManager | Hibernate Session |
|---|---|---|
| Nguồn API | Chuẩn Jakarta Persistence | API native của Hibernate |
| Mục tiêu | Tính di động giữa các JPA provider | Khả năng và tính năng đặc thù Hibernate |
| Persistence context | Có | Có |
| Dirty checking và first-level cache | Có | Có |
| Transaction | Phối hợp với resource-local hoặc JTA transaction | Phối hợp với transaction theo cấu hình Hibernate/JTA |
| Query | JPQL, Criteria, native SQL | HQL/JPQL và các API query Hibernate |
| Lifecycle | Do ứng dụng hoặc container quản lý tùy cách tạo | Do ứng dụng hoặc framework tích hợp quản lý |
| Khả năng dùng thay thế | API chuẩn, phù hợp khi muốn giảm phụ thuộc provider | Phù hợp khi cần API native và tính năng Hibernate |

Không nên tạo cả EntityManager và Session độc lập cho cùng một công việc chỉ vì nghĩ chúng là hai lớp bắt buộc. Nếu ứng dụng dùng JPA, hãy ưu tiên EntityManager trong mã nghiệp vụ và chỉ lấy Session thông qua cơ chế unwrap khi thực sự cần tính năng Hibernate. Nếu ứng dụng dùng native Hibernate, quản lý Session theo lifecycle của Hibernate.

## 4. Persistence context là gì?

Persistence context là phạm vi trong đó provider quản lý các entity. Một entity được quản lý (*managed*) sẽ được theo dõi. Khi thuộc tính thay đổi, provider có thể phát hiện thay đổi bằng dirty checking và đồng bộ xuống database trong lần flush phù hợp.

Một persistence context thường có first-level cache. Nếu một entity đã được tải trong cùng context, lần truy cập tiếp theo theo cùng khóa có thể trả lại cùng instance Java mà không phải đọc lại database. Điều này giúp bảo đảm identity của entity trong một đơn vị làm việc.

Các trạng thái entity thường được mô tả như sau:

| Trạng thái | Ý nghĩa |
|---|---|
| New / transient | Đối tượng mới, chưa được persistence context quản lý |
| Managed / persistent | Entity nằm trong persistence context và được theo dõi |
| Detached | Entity từng được quản lý nhưng đã tách khỏi context hoặc context đã đóng |
| Removed | Entity được đánh dấu xóa trong persistence context |

Ví dụ:

```java
Product product = em.find(Product.class, 10L); // managed
product.setPrice(49.00);                       // dirty checking
em.flush();                                    // đồng bộ SQL
em.detach(product);                            // detached
```

Khi EntityManager hoặc Session đóng, persistence context của nó kết thúc. Các entity không còn được quản lý trong context đó. Điều này quan trọng với CRaC: không nên giữ một persistence context dài hạn chứa entity, proxy lazy hoặc trạng thái giao dịch dở dang qua checkpoint rồi giả định rằng nó có thể tiếp tục làm việc như trước.

## 5. EntityManager/Session không phải đối tượng dùng chung toàn ứng dụng

Một EntityManager hoặc Hibernate Session thông thường không thread-safe. Nó đại diện cho một đơn vị làm việc với persistence context có trạng thái. Nhiều thread cùng dùng một Session có thể gây race condition, lỗi trạng thái entity, transaction hoặc JDBC resource.

Mô hình thường dùng là:

- EntityManagerFactory hoặc SessionFactory được chia sẻ trong ứng dụng.
- Mỗi request, transaction hoặc đơn vị công việc có EntityManager/Session riêng.
- Transaction được bắt đầu và kết thúc trong phạm vi rõ ràng.
- EntityManager/Session được đóng hoặc trả về framework sau khi đơn vị công việc kết thúc.

Trong môi trường container, ứng dụng có thể inject một EntityManager proxy. Proxy tìm hoặc lấy EntityManager phù hợp với transaction/thread hiện tại. Điều này không có nghĩa đối tượng persistence context thực sự có thể được chia sẻ giữa mọi thread. Hãy tuân thủ quy tắc transaction và concurrency của framework.

Không lưu EntityManager hoặc Session trong static field, singleton dùng chung hoặc object cache toàn ứng dụng để tái sử dụng giữa các request. Cũng không truyền chúng vào executor để một thread khác tiếp tục thao tác nếu framework không hỗ trợ rõ ràng mô hình đó.

## 6. EntityManagerFactory và SessionFactory có vòng đời khác

EntityManagerFactory và SessionFactory là các factory tạo EntityManager hoặc Session. Chúng thường được tạo một lần khi ứng dụng khởi động và dùng trong suốt vòng đời ứng dụng.

Các factory này có thể giữ:

- Metadata ánh xạ entity và schema.
- Cấu hình provider và dịch vụ nội bộ.
- Query plan cache hoặc metadata cache.
- Second-level cache nếu được bật.
- Connection provider hoặc tham chiếu đến DataSource.
- Thành phần quản lý transaction và tích hợp với framework.
- Một số thread hoặc tài nguyên nội bộ tùy provider và cấu hình.

Thông thường, factory được thiết kế để chia sẻ giữa nhiều thread, còn EntityManager/Session là đối tượng ngắn hạn. Factory có chi phí khởi tạo đáng kể nên không nên tạo mới cho mỗi request.

Khi dùng CRaC, không nên mặc định phải đóng EntityManagerFactory hoặc SessionFactory trước mọi checkpoint. Cần xem xét tích hợp CRaC của đúng phiên bản provider, cache, connection provider và framework. Có trường hợp factory có thể được giữ lại sau restore khi mọi tài nguyên phụ thuộc đã được xử lý đúng. Có trường hợp tích hợp yêu cầu đóng hoặc tái tạo một số thành phần. Quyết định phải dựa trên tài liệu và kiểm thử, không phải giả định chung.

## 7. Các tài nguyên dữ liệu phía sau EntityManager và Session

Một thao tác ORM có thể sử dụng nhiều tài nguyên bên dưới:

### 7.1. DataSource và connection pool

DataSource cung cấp JDBC Connection. Connection pool giữ các kết nối vật lý và cấp connection cho transaction. Pool thường sống lâu hơn một EntityManager hoặc Session.

Connection vật lý có thể bị database đóng, hết timeout, mất socket hoặc không còn hợp lệ sau khi tiến trình được checkpoint và khôi phục. Vì vậy, cần dùng CRaC integration của pool nếu có; nếu không, xác định cách pool tạm dừng, đóng kết nối và tạo kết nối mới sau restore.

### 7.2. JDBC Connection

Connection thường được lấy khi transaction bắt đầu hoặc khi provider cần truy cập database. Connection gắn với transaction, isolation level, auto-commit, session variables và trạng thái phía database.

Không nên checkpoint khi transaction còn active và giả định connection sẽ tiếp tục như cũ sau restore. Cần hoàn tất hoặc rollback transaction trước checkpoint theo quy tắc của ứng dụng.

### 7.3. Statement, PreparedStatement và ResultSet

Các đối tượng JDBC này có thể giữ tài nguyên phía driver hoặc database. Một ResultSet đang mở có thể phụ thuộc cursor phía server, connection và vị trí đọc. Hãy đóng hoặc hoàn tất chúng trước checkpoint. Với truy vấn streaming hoặc xử lý batch lớn, cần lưu tiến độ bền vững và tạo truy vấn mới sau restore thay vì giữ cursor cũ.

### 7.4. Transaction và transaction manager

Transaction có trạng thái ở cả ứng dụng, driver và database. Một transaction đang active không nên được xem như trạng thái có thể nhân bản an toàn. Trước checkpoint, hãy ngừng tạo transaction mới, chờ transaction đang chạy hoàn tất hoặc rollback theo chính sách. Nếu dùng JTA hoặc distributed transaction, cần tuân thủ coordinator và transaction manager tương ứng.

### 7.5. Cache

Hibernate có first-level cache trong từng persistence context. Second-level cache có thể nằm trong bộ nhớ ứng dụng hoặc dùng cache provider bên ngoài. Query cache cũng có lifecycle và quy tắc invalidation riêng.

First-level cache kết thúc cùng EntityManager/Session. Second-level cache có thể được giữ nếu provider hỗ trợ và dữ liệu còn hợp lệ, nhưng cần xem xét invalidation, cluster consistency và tài nguyên của cache provider. Không coi cache trong heap của một tiến trình là nguồn dữ liệu chính thức.

## 8. Điều gì có thể xảy ra nếu checkpoint khi EntityManager hoặc Session còn hoạt động?

Giả sử một request thực hiện:

1. Mở EntityManager.
2. Bắt đầu transaction.
3. Tải một entity và sửa một số thuộc tính.
4. Provider giữ entity trong persistence context và có thể đã lấy JDBC Connection.
5. Ứng dụng bị checkpoint trước khi transaction commit.

Sau restore, có nhiều khả năng không còn đúng như trạng thái ban đầu:

- Database có thể đã rollback transaction khi connection bị ngắt.
- Connection trong pool có thể đã bị server đóng hoặc không còn hợp lệ.
- Persistence context trong heap có thể vẫn chứa entity với trạng thái thay đổi chưa được commit.
- Provider có thể giữ tham chiếu đến JDBC resource hoặc transaction cũ.
- Lazy proxy hoặc collection có thể cần Session cũ đã đóng.
- Request đang xử lý có thể không được tiếp tục từ đúng ranh giới nghiệp vụ.

Nếu ứng dụng tiếp tục dùng persistence context đó, có thể gặp exception, dữ liệu stale, transaction không hợp lệ hoặc thao tác ghi lặp. CRaC không biến transaction database thành transaction có thể pause và resume qua mọi môi trường.

Thiết kế an toàn là tạo checkpoint khi không có đơn vị công việc dữ liệu đang hoạt động. Sau restore, mỗi request hoặc job mới tạo một persistence context và transaction mới.

## 9. Flush, commit và close trong JPA/Hibernate

Ba thao tác này có ý nghĩa khác nhau:

| Thao tác | Ý nghĩa |
|---|---|
| flush() | Đồng bộ thay đổi của persistence context xuống database bằng SQL |
| commit() | Hoàn tất transaction theo transaction manager/database |
| close() | Kết thúc EntityManager/Session và giải phóng tài nguyên thuộc phạm vi của nó |

flush() không đồng nghĩa với commit(). SQL có thể đã được gửi đến database nhưng transaction vẫn chưa commit. Nếu transaction rollback, các thay đổi vẫn có thể bị hủy. Ngược lại, commit thường kích hoạt flush trước khi hoàn tất transaction, tùy chế độ flush và provider.

Trước checkpoint, không nên chỉ gọi em.flush() rồi coi dữ liệu đã an toàn. Hãy xác định transaction owner và commit hoặc rollback theo ranh giới nghiệp vụ. Sau khi transaction kết thúc, đóng EntityManager/Session do ứng dụng sở hữu.

Ví dụ:

```java
EntityManager em = entityManagerFactory.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    // Thực hiện các thay đổi trong một đơn vị công việc.
    updateProduct(em, 10L);

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Trong ứng dụng thực tế, transaction manager có thể sở hữu transaction và EntityManager. Khi đó, hãy để framework hoàn tất transaction và đóng persistence context theo lifecycle đã cấu hình. Không tự gọi commit/close lên một đối tượng được container quản lý nếu hợp đồng của framework không cho phép.

## 10. Quản lý EntityManager trong các mô hình ứng dụng

### 10.1. Application-managed EntityManager

Ứng dụng gọi EntityManagerFactory.createEntityManager() và chịu trách nhiệm đóng EntityManager. Đây là mô hình dễ nhìn thấy lifecycle và có thể phù hợp với ứng dụng Java SE hoặc một số thành phần độc lập.

Mỗi đơn vị công việc nên tạo EntityManager, bắt đầu transaction, xử lý và đóng trong finally hoặc try/finally tương đương. Không lưu EntityManager sau khi đơn vị công việc hoàn tất.

### 10.2. Container-managed EntityManager

Trong ứng dụng Jakarta EE hoặc môi trường container, EntityManager được inject và lifecycle do container quản lý. Persistence context có thể được gắn với transaction hoặc scope được chỉ định. Ứng dụng không tự ý đóng EntityManager container-managed.

Khi dùng CRaC, cần làm việc qua lifecycle integration của container. Coordinator phải ngăn request mới và chờ transaction hiện tại kết thúc; container hoặc provider thực hiện thao tác tương ứng trên persistence context.

### 10.3. Spring-managed EntityManager

Trong ứng dụng Spring, EntityManager thường được inject thông qua proxy và được liên kết với transaction hiện tại. @Transactional điều khiển transaction boundary; Spring quản lý việc bind/unbind tài nguyên phù hợp.

Không nên giữ EntityManager proxy hoặc đối tượng transaction-scoped trong một thread nền rồi sử dụng sau khi transaction đã kết thúc. Với CRaC, cần dừng ingress và background task, để transaction manager hoàn tất transaction, rồi để Spring/provider thực hiện cleanup theo integration tương ứng.

### 10.4. Hibernate Session mở theo request

Nếu ứng dụng dùng native Session, cần xác định nơi mở Session và nơi đóng. Pattern phổ biến là một Session cho mỗi đơn vị công việc, transaction được kết thúc rõ ràng và Session đóng ngay sau đó. Không dùng Session như một singleton.

## 11. Quy trình chuẩn bị tài nguyên JPA/Hibernate trước checkpoint

Một quy trình tổng quát nên phối hợp request, transaction manager, persistence provider và connection pool.

1. Ngừng nhận request mới và dừng consumer/scheduler tạo công việc truy cập database.
2. Chờ các request, job và message handler đang chạy hoàn tất trong giới hạn thời gian.
3. Xác nhận không còn transaction active trong phạm vi ứng dụng.
4. Đóng EntityManager/Session application-managed còn mở; để container-managed context được container cleanup theo lifecycle.
5. Đóng cursor, ResultSet, stream query và JDBC resource còn tồn tại.
6. Xử lý connection pool và client theo CRaC integration của đúng phiên bản.
7. Xác nhận factory/cache có thể được giữ lại hoặc cần tái tạo theo tài liệu provider.
8. Chỉ cho phép checkpoint khi coordinator nhận xác nhận từ các thành phần sở hữu tài nguyên dữ liệu.

Không nên viết một callback chung chỉ gọi close() trên tất cả đối tượng có tên EntityManager. Một số đối tượng có thể là proxy container-managed; một số đã được đóng; một số thuộc transaction đang hoạt động. Phải phân biệt owner và loại lifecycle.

## 12. Vai trò của CRaC Resource và coordinator

CRaC cung cấp Resource API với hai callback:

- beforeCheckpoint(...): chuẩn bị tài nguyên trước khi lưu trạng thái tiến trình.
- afterRestore(...): phục hồi hoặc tạo lại tài nguyên sau khi khôi phục.

Với database access, thường có nhiều component phải phối hợp. Một coordinator có thể ngừng ingress, chờ transaction kết thúc và yêu cầu owner của pool/client chuẩn bị tài nguyên. Mỗi owner quản lý chi tiết đối tượng mình tạo.

Mô hình trách nhiệm:

| Thành phần | Trách nhiệm trước checkpoint | Trách nhiệm sau restore |
|---|---|---|
| HTTP server / message listener | Ngừng nhận công việc mới, drain request/message | Mở lại traffic sau readiness |
| Transaction manager | Chờ transaction kết thúc hoặc rollback theo chính sách | Bắt đầu transaction mới cho công việc mới |
| EntityManager/Session owner | Đóng persistence context do ứng dụng sở hữu | Tạo context mới khi có đơn vị công việc |
| DataSource/connection pool owner | Dừng cấp connection, đóng hoặc chuẩn bị pool theo integration | Tạo/kiểm tra kết nối mới |
| EntityManagerFactory/SessionFactory owner | Xác minh factory có thể giữ lại theo provider | Tái tạo nếu integration yêu cầu |
| Cache provider owner | Flush/invalidate hoặc giữ cache theo chính sách | Kiểm tra tính hợp lệ và kết nối cache |
| Coordinator | Xác nhận các thành phần đã quiesce | Chỉ cho phép readiness khi dependency sẵn sàng |

Ví dụ dưới đây minh họa một coordinator adapter ở mức khái quát. Các phương thức của DatabaseLifecycle là hợp đồng ứng dụng tự định nghĩa; chúng không phải API chuẩn của JPA hoặc Hibernate.

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class DatabaseCheckpointResource implements Resource {
    private final DatabaseLifecycle lifecycle;

    public DatabaseCheckpointResource(DatabaseLifecycle lifecycle) {
        this.lifecycle = lifecycle;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        lifecycle.stopNewWork();
        lifecycle.awaitTransactionsToFinish();
        lifecycle.closeApplicationManagedPersistenceContexts();
        lifecycle.prepareConnectionProvider();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        lifecycle.restoreConnectionProvider();
        lifecycle.validatePersistenceInfrastructure();
        lifecycle.allowNewWork();
    }

    public interface DatabaseLifecycle {
        void stopNewWork() throws Exception;
        void awaitTransactionsToFinish() throws Exception;
        void closeApplicationManagedPersistenceContexts() throws Exception;
        void prepareConnectionProvider() throws Exception;
        void restoreConnectionProvider() throws Exception;
        void validatePersistenceInfrastructure() throws Exception;
        void allowNewWork() throws Exception;
    }
}
```

Ví dụ này mô tả trách nhiệm điều phối chứ không phải implementation có thể cắm trực tiếp vào mọi ứng dụng. Trong thực tế, cần bảo đảm allowNewWork() chỉ chạy sau khi tất cả resource thiết yếu đã phục hồi. Nếu một bước thất bại, ứng dụng phải giữ trạng thái chưa ready và báo lỗi rõ ràng. Không được mở traffic chỉ vì callback afterRestore() đã bắt đầu.

## 13. EntityManagerFactory và SessionFactory sau restore

Factory thường được dùng suốt vòng đời ứng dụng và có thể chứa metadata/cache có giá trị. Tuy nhiên, nó có thể tham chiếu đến connection provider, cache provider, transaction platform hoặc service nội bộ. Vì vậy, câu hỏi không chỉ là “factory có nằm trong heap không?” mà là “mọi dependency mà factory sử dụng có hợp lệ sau restore không?”.

Có ba hướng thiết kế, tùy provider và phiên bản:

- **Giữ factory và phục hồi dependency:** Chỉ phù hợp khi provider và các tích hợp được xác nhận hỗ trợ CRaC, đồng thời các kết nối hoặc service bên dưới được phục hồi đúng cách.
- **Tái tạo một số dependency:** Giữ metadata/factory nếu được hỗ trợ, nhưng tạo lại pool hoặc client mà factory sử dụng.
- **Đóng và tạo lại factory:** Chỉ chọn khi tài liệu provider hoặc kết quả kiểm thử yêu cầu. Cần tính chi phí khởi tạo, cache bị mất và thứ tự tạo lại các bean phụ thuộc.

Không nên đóng SessionFactory/EntityManagerFactory một cách tùy tiện trong callback nếu framework đang quản lý chúng. Việc đóng factory có thể làm hỏng các service đang giữ reference hoặc khiến container không thể tiếp tục hoạt động. Hãy đặt trách nhiệm ở component tạo factory và tuân theo lifecycle của framework.

## 14. Cache và tính nhất quán dữ liệu

Hibernate có first-level cache trong từng Session. JPA có persistence context tương ứng trong EntityManager. Những cache này gắn với một đơn vị công việc và kết thúc khi context đóng.

Second-level cache thường được chia sẻ giữa các Session trong cùng factory. Nó có thể nằm trong heap của tiến trình hoặc được quản lý bởi cache provider bên ngoài. Khi checkpoint/restore, cần trả lời:

- Cache có chứa dữ liệu thay đổi sau checkpoint không?
- Database có thể được cập nhật bởi tiến trình khác trong thời gian ảnh được lưu không?
- Cache provider có hỗ trợ CRaC không?
- Cache có cần reconnect hoặc rejoin cluster sau restore không?
- TTL và invalidation có tiếp tục chính xác không?
- Nhiều instance restore từ cùng checkpoint có tạo ra các bản cache cục bộ giống nhau nhưng sau đó phân kỳ không?

Nếu cache là dữ liệu có thể tái tạo, invalidation hoặc warm-up lại sau restore có thể đơn giản hơn việc cố giữ mọi trạng thái. Nếu dùng distributed cache, cần phục hồi kết nối và kiểm tra cluster membership. Không dùng cache trong heap làm nguồn sự thật cho trạng thái nghiệp vụ.

## 15. Truy vấn streaming, cursor và xử lý dữ liệu lớn

Một số API trả về stream hoặc cursor để xử lý dữ liệu lớn mà không tải toàn bộ kết quả vào bộ nhớ. Ví dụ, Hibernate có thể hỗ trợ scroll hoặc stream query tùy API; JDBC ResultSet có thể giữ cursor phía database.

Những tài nguyên này thường phụ thuộc vào Session, transaction và connection. Không nên giữ cursor đang mở qua checkpoint. Thay vào đó:

1. Ngừng nhận công việc mới.
2. Hoàn tất hoặc đóng stream/cursor đang mở.
3. Lưu tiến độ xử lý theo khóa hoặc sequence bền vững.
4. Đóng persistence context và transaction.
5. Sau restore, mở transaction và query mới từ vị trí đã xác nhận.

Cần cẩn thận với offset pagination trên bảng có thay đổi đồng thời. Nếu dữ liệu bị thêm/xóa trong lúc checkpoint, offset có thể bỏ sót hoặc đọc lặp. Keyset pagination theo khóa ổn định hoặc cơ chế snapshot/lease phù hợp có thể an toàn hơn, tùy yêu cầu nghiệp vụ.

## 16. Giao dịch và nguy cơ mất hoặc lặp dữ liệu

Checkpoint không tạo một transaction phân tán giữa heap Java và database. Một request có thể commit database thành công nhưng chưa ghi nhận kết quả trong trạng thái ứng dụng, hoặc cập nhật trạng thái trong heap trước khi transaction commit.

Ví dụ có nguy cơ lặp:

1. Request tạo đơn hàng và database commit thành công.
2. Ứng dụng chưa ghi nhận request đã hoàn tất.
3. Tiến trình bị checkpoint hoặc dừng ở trạng thái chưa đồng bộ.
4. Sau restore, công việc được gửi lại.
5. Nếu không có idempotency key, đơn hàng thứ hai có thể được tạo.

Ví dụ có nguy cơ mất:

1. Ứng dụng tăng bộ đếm tiến độ trong heap.
2. Transaction database chưa commit.
3. Checkpoint lưu bộ đếm đã tăng.
4. Sau restore, ứng dụng tiếp tục từ bản ghi kế tiếp.
5. Thay đổi database chưa commit đã bị rollback và không được gửi lại.

Cách xử lý:

- Dùng idempotency key ổn định cho thao tác có side effect.
- Lưu progress trong cùng transaction với thay đổi nghiệp vụ khi có thể.
- Dùng transactional outbox khi cần phối hợp cập nhật database và phát event.
- Chỉ xác nhận message hoặc tăng offset sau khi transaction đã commit theo hợp đồng.
- Không đưa transaction active vào checkpoint.
- Khi kết quả commit không rõ ràng, tra cứu trạng thái bằng operation ID trước khi retry.

## 17. Các lỗi thường gặp khi dùng JPA/Hibernate với CRaC

**Giữ EntityManager hoặc Session trong singleton.** Persistence context có trạng thái và không thread-safe. Tạo context theo transaction hoặc đơn vị công việc và kết thúc đúng lifecycle.

**Chia sẻ Session giữa nhiều thread.** Điều này có thể gây race condition và lỗi transaction. Mỗi đơn vị công việc cần context riêng.

**Checkpoint khi transaction đang active.** Database có thể rollback hoặc connection không còn hợp lệ. Drain công việc và kết thúc transaction trước checkpoint.

**Cho rằng flush() là commit().** Flush chỉ đồng bộ persistence context xuống database; transaction vẫn có thể rollback. Hãy để transaction manager commit hoặc rollback.

**Đóng EntityManager container-managed bằng tay.** Việc này có thể phá vỡ lifecycle do framework quản lý. Phân biệt application-managed với container-managed.

**Giữ ResultSet hoặc stream query qua checkpoint.** Cursor phụ thuộc connection/session và có thể không còn hợp lệ. Đóng cursor và lưu tiến độ bền vững.

**Đóng factory nhưng không phối hợp với framework.** SessionFactory hoặc EntityManagerFactory có thể đang được nhiều bean sử dụng. Quản lý chúng ở đúng owner và theo integration của provider.

**Giữ connection pool với socket cũ.** Connection có thể đã bị database đóng. Dùng integration được hỗ trợ hoặc tạo lại pool/kết nối theo hướng dẫn.

**Tin rằng cache trong heap luôn mới.** Database có thể thay đổi trong thời gian checkpoint được lưu. Xác minh TTL, invalidation và consistency sau restore.

**Mở traffic trước khi database sẵn sàng.** Callback restore có thể chưa tạo xong pool hoặc xác thực kết nối. Readiness phải đợi persistence infrastructure hoạt động.

## 18. Quy trình kiểm thử JPA/Hibernate sau restore

Một bài kiểm thử nên dùng đúng JDK CRaC, phiên bản provider, connection pool, database và môi trường triển khai dự kiến.

### Kiểm thử vòng đời cơ bản

1. Khởi chạy ứng dụng và xác nhận EntityManagerFactory/SessionFactory đã được tạo.
2. Gửi một request tạo hoặc cập nhật dữ liệu, xác nhận transaction commit.
3. Yêu cầu ứng dụng quiesce và tạo checkpoint.
4. Restore tiến trình từ checkpoint.
5. Xác nhận connection pool hoặc connection provider đã phục hồi.
6. Gửi request mới, tạo EntityManager/Session mới và thực hiện query.
7. Kiểm tra kết quả database, log, metric và readiness.

### Kiểm thử transaction đang chạy

Tạo một request giữ transaction trong một khoảng thời gian kiểm soát được. Yêu cầu checkpoint trong lúc request đang chạy. Coordinator phải ngừng nhận việc mới và chờ transaction hoàn tất hoặc rollback theo chính sách. Xác nhận checkpoint không xảy ra khi transaction còn active.

### Kiểm thử database bị ngắt kết nối

Sau khi tạo checkpoint, có thể chủ động đóng hoặc làm hết hạn kết nối trong môi trường kiểm thử trước khi restore. Xác nhận ứng dụng tạo connection mới, không dùng lại socket cũ và không báo ready khi pool chưa hoạt động.

### Kiểm thử query stream

Mở truy vấn streaming, xử lý một phần dữ liệu rồi yêu cầu quiesce. Xác nhận cursor được đóng, tiến độ được lưu đúng và sau restore truy vấn mới tiếp tục từ vị trí phù hợp mà không bỏ sót hoặc xử lý lặp ngoài dự kiến.

### Kiểm thử nhiều instance

Nếu dùng cùng ảnh để restore nhiều instance, xác nhận mỗi instance tạo persistence context và connection riêng. Kiểm tra connection pool tổng thể không vượt giới hạn database, transaction không bị dùng chung và cache nhất quán theo thiết kế.

Các chỉ số nên thu thập:

- Thời gian restore đến khi DataSource sẵn sàng.
- Thời gian đến query đầu tiên thành công.
- Số connection active/idle và số lần connection validation thất bại.
- Số transaction active tại thời điểm chuẩn bị checkpoint.
- Số lỗi EntityManager/Session và lỗi SQL sau restore.
- Thời gian tạo EntityManagerFactory/SessionFactory nếu phải tái tạo.
- Cache hit/miss và invalidation.
- p95/p99 latency của request truy cập database.
- Số transaction rollback, retry và thao tác nghiệp vụ trùng.

## 19. Checklist cho EntityManager, Session và tài nguyên dữ liệu

- [ ] Đã phân biệt EntityManager/Session với EntityManagerFactory/SessionFactory chưa?
- [ ] Đã xác định EntityManager/Session nào application-managed và cái nào container-managed chưa?
- [ ] Mỗi persistence context có phạm vi transaction hoặc đơn vị công việc rõ ràng chưa?
- [ ] Có EntityManager/Session nào bị giữ trong static field, singleton hoặc truyền qua thread không?
- [ ] Đã xác định owner của DataSource, connection pool, transaction manager và cache provider chưa?
- [ ] Request, consumer và scheduler có được drain trước checkpoint không?
- [ ] Không còn transaction active hoặc cursor/ResultSet/stream query mở khi checkpoint chưa?
- [ ] EntityManager/Session do ứng dụng sở hữu đã được đóng đúng cách chưa?
- [ ] Connection pool và provider có CRaC integration phù hợp với phiên bản đang dùng không?
- [ ] EntityManagerFactory/SessionFactory được giữ lại hay tái tạo dựa trên tài liệu provider chưa?
- [ ] Cache có chính sách invalidation và kiểm tra freshness sau restore chưa?
- [ ] Transaction progress và side effect có idempotency hoặc cơ chế bền vững chưa?
- [ ] Readiness có chờ database connection và query kiểm tra thành công chưa?
- [ ] Đã kiểm thử restore, database disconnect, transaction drain và query stream chưa?

## Kết luận

EntityManager và Hibernate Session đại diện cho persistence context và thường gắn với một transaction hoặc đơn vị công việc ngắn hạn. Chúng theo dõi entity, dirty checking, cache cấp một và phối hợp đồng bộ dữ liệu với database. EntityManagerFactory và SessionFactory là factory dài hạn, thường được chia sẻ và có vòng đời khác. Phía sau các đối tượng này còn có DataSource, connection pool, JDBC connection, transaction manager, cursor, cache và các dịch vụ nền.

Để dùng CRaC an toàn, hãy kết thúc đơn vị công việc đang hoạt động trước checkpoint, không giữ EntityManager/Session hoặc transaction dở dang qua restore, và quản lý connection pool theo tích hợp được hỗ trợ. Sau restore, tạo persistence context mới cho request mới, xác minh kết nối và cache, rồi mới mở traffic. Khi owner và lifecycle của từng thành phần được xác định rõ, ứng dụng có thể tận dụng checkpoint/restore mà vẫn giữ được tính nhất quán của dữ liệu.

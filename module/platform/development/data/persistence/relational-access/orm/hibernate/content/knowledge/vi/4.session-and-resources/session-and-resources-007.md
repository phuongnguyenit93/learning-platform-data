# Session hiện tại và cơ chế liên kết với ngữ cảnh thực thi trong Hibernate

Trong Hibernate ORM, một `Session` là nơi ứng dụng thực hiện các thao tác persistence như lưu, tìm, truy vấn, cập nhật hoặc xóa entity. Câu hỏi thường gặp là: **khi nhiều lớp cùng truy cập dữ liệu, làm sao chúng sử dụng đúng Session đang phục vụ một đơn vị công việc?**

Hibernate cung cấp phương thức:

```java
Session session = sessionFactory.getCurrentSession();
```

Tuy nhiên, “current Session” **không đơn giản là Session được tạo gần đây nhất**, không phải Session duy nhất trên toàn ứng dụng, và cũng không có nghĩa nó luôn tự xuất hiện ở bất kỳ thread nào. Hibernate cần một **cơ chế xác định ngữ cảnh thực thi** (*current-session context*) để biết Session nào là “hiện tại”.

Bài học làm rõ ý nghĩa của Session hiện tại, sự khác nhau giữa `getCurrentSession()` và `openSession()`, các cách liên kết Session với thread hoặc transaction, quyền sở hữu vòng đời tài nguyên và những bẫy khi dùng cơ chế này trong ứng dụng nhiều luồng.

## 1. Session, SessionFactory và persistence context

Ba khái niệm có phạm vi khác nhau:

- **`SessionFactory`**: đối tượng tạo và quản lý các Session, chứa metadata mapping và các cấu hình dùng chung. Thường được xây dựng một lần cho một cấu hình persistence và chia sẻ an toàn giữa các luồng.
- **`Session`**: đối tượng làm việc với persistence trong một khoảng thời gian hữu hạn, cho phép thao tác entity và truy vấn. Nó là API native của Hibernate, gần với vai trò `EntityManager` của Jakarta Persistence.
- **Persistence context**: tập hợp entity đang được quản lý trong Session, kèm identity map và trạng thái thay đổi cần đồng bộ. Trong Hibernate ORM thông thường, một Session bao bọc một persistence context gắn với vòng đời Session đó.

Ví dụ:

```java
import org.hibernate.Session;
import org.hibernate.SessionFactory;

public final class ProductReader {
    private final SessionFactory sessionFactory;

    public ProductReader(SessionFactory sessionFactory) {
        this.sessionFactory = sessionFactory;
    }

    public Product find(Long id) {
        Session session = sessionFactory.getCurrentSession();
        return session.find(Product.class, id);
    }
}
```

Ví dụ giả định `Product` là entity đã mapping **và môi trường đã cấu hình current-session context thích hợp**. Chỉ gọi `getCurrentSession()` mà chưa cấu hình ngữ cảnh có thể thất bại; phần sau giải thích khi nào phương thức này hoạt động.

Một điểm quan trọng: **Session không an toàn để chia sẻ đồng thời giữa các luồng**. Nhiều service có thể chia sẻ cùng một `SessionFactory`, nhưng mỗi đơn vị công việc nên sử dụng Session theo phạm vi và quản lý transaction phù hợp.

## 2. “Session hiện tại” nghĩa là gì?

`SessionFactory.getCurrentSession()` yêu cầu Hibernate tìm Session thuộc **ngữ cảnh hiện hành**. Ngữ cảnh có thể được xác định bằng:

- Transaction JTA đang chạy;
- Thread đang thực thi, theo chiến lược `thread`;
- Một Session được ứng dụng hoặc framework chủ động gắn vào context, theo chiến lược `managed`;
- Cơ chế tùy biến thông qua một implementation `CurrentSessionContext`.

Mô hình tư duy:

```text
                SessionFactory
                     |
          getCurrentSession()
                     |
                     v
             CurrentSessionContext
                     |
          tìm theo ngữ cảnh hiện hành
               /      |       \
             JTA    Thread   Managed
               \      |       /
                     |
                     v
          Session thuộc đơn vị công việc
                     |
                     v
             Persistence context
                     |
                     v
                 JDBC / DB
```

Nếu hai lời gọi diễn ra trong **cùng ngữ cảnh được cấu hình** và Session vẫn còn hợp lệ, chúng thường nhận cùng Session được quản lý cho ngữ cảnh đó:

```java
Session first = sessionFactory.getCurrentSession();
Session second = sessionFactory.getCurrentSession();

// Trong cùng một context còn hoạt động:
boolean same = first == second; // thông thường true
```

Điều đó **không có nghĩa** mọi nơi gọi `getCurrentSession()` đều nhận cùng Session. Các transaction, thread hoặc ngữ cảnh được bind khác nhau có thể có các Session khác nhau.

Ví dụ hai request độc lập:

```text
Request A / Transaction A -> Session A -> persistence context A
Request B / Transaction B -> Session B -> persistence context B
                               ^
                               |
                       chung SessionFactory
```

Session A và Session B có thể cùng đọc một hàng dữ liệu nhưng giữ hai instance entity khác nhau trong hai persistence context. Identity map cấp Session không tự tạo ra một bộ nhớ entity dùng chung trên toàn ứng dụng.

## 3. `openSession()` khác gì `getCurrentSession()`?

Hai phương thức dùng để nhận Session nhưng thể hiện **hai mô hình sở hữu** khác nhau.

| Nội dung | `sessionFactory.openSession()` | `sessionFactory.getCurrentSession()` |
|---|---|---|
| Mục đích | Mở một Session mới | Lấy Session của ngữ cảnh hiện tại |
| Quan hệ với context | Không tự đặt Session mới vào current-session context | Ủy quyền cho `CurrentSessionContext` |
| Giá trị trả về giữa các lần gọi | Mỗi lần gọi tạo Session mới | Có thể cùng Session khi cùng context còn hiệu lực |
| Cần cấu hình current-session context? | Không | Có, bằng cấu hình hoặc tích hợp tương đương |
| Ai quản lý đóng Session? | Bên mở Session, trừ khi chuyển giao ownership rõ ràng | Tùy chiến lược context và framework quản lý |
| Phù hợp | Tác vụ độc lập, tài nguyên do caller trực tiếp kiểm soát | Nhiều thành phần tham gia cùng một unit of work |
| Rủi ro điển hình | Quên `close()`, tạo nhiều Session cho cùng luồng nghiệp vụ | Không có Session bound, cấu hình context sai, hiểu nhầm ai sẽ đóng |

Ví dụ tự mở và tự đóng Session:

```java
import org.hibernate.Session;
import org.hibernate.Transaction;

public Product loadProduct(SessionFactory sessionFactory, Long id) {
    try (Session session = sessionFactory.openSession()) {
        Transaction tx = session.beginTransaction();
        try {
            Product product = session.find(Product.class, id);
            tx.commit();
            return product;
        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                tx.rollback();
            }
            throw ex;
        }
    }
}
```

Đây là một cách làm rõ quyền sở hữu: caller mở Session bằng `openSession()`, thực hiện transaction, sau đó đóng Session bằng `try-with-resources`. Mã trả về entity đã tách khỏi Session khi hàm kết thúc; truy cập quan hệ lazy chưa được tải lúc ấy có thể gây lỗi.

Nếu thay `openSession()` bằng `getCurrentSession()` trong ví dụ trên, **không nên máy móc giữ lại `try-with-resources`**. Session hiện tại có thể thuộc sở hữu của transaction manager hoặc môi trường tích hợp; tự đóng nó giữa transaction sẽ phá vỡ vòng đời đã được quản lý.

## 4. Điểm mở rộng cốt lõi: `CurrentSessionContext`

Hibernate sử dụng contract `org.hibernate.context.spi.CurrentSessionContext` để thực hiện cách chọn current Session cho một `SessionFactory`. Các chiến lược context tiêu biểu được cấu hình qua thuộc tính:

```properties
hibernate.current_session_context_class=...
```

Giá trị có thể là một strategy được Hibernate hỗ trợ, chẳng hạn `jta`, `thread`, `managed`, hoặc tên lớp implementation context thích hợp mà ứng dụng cung cấp.

Ví dụ phân biệt:

| Context | Khóa liên kết logic | Ai gắn/tìm Session? | Điểm đáng nhớ |
|---|---|---|---|
| `jta` | Transaction JTA đang hoạt động | Hibernate dựa vào hạ tầng JTA và synchronization | Dùng trong môi trường có JTA thực sự |
| `thread` | Thread hiện tại | `ThreadLocalSessionContext` | Hữu ích cho mô hình Session per thread/unit of work; không nên đánh đồng thread với request |
| `managed` | Session được bind với thread hiện hành | `ManagedSessionContext` và code/framework gọi bind/unbind | Ứng dụng phải quản lý rõ việc mở, bind, unbind và close |
| Custom context | Phụ thuộc implementation | `CurrentSessionContext` riêng | Cần hiểu lifecycle, concurrency và transaction integration |

Cần phân biệt hai khái niệm đôi khi được gọi giống nhau:

- **Current-session context** quyết định *Session nào* gắn với ngữ cảnh.
- **Transaction context** quyết định *transaction nào* bao bọc các lệnh SQL và khi nào commit/rollback.

Chúng thường đi cùng nhau, nhưng không đồng nhất. Một Session có thể tồn tại trước khi transaction bắt đầu hoặc trong một khoảng thời gian ngắn hơn transaction tùy mô hình tích hợp. Việc có current Session **không bảo đảm** đang có transaction hợp lệ.

### Lưu ý theo phiên bản Hibernate

Tên property trên là cơ chế cấu hình quen thuộc của Hibernate ORM. Cách khởi tạo context, mặc định khi có hạ tầng JTA, tương tác với transaction manager và những chi tiết lifecycle có thể thay đổi theo phiên bản/framework. Trước khi chọn một strategy, cần đối chiếu tài liệu của **phiên bản Hibernate thực tế** và cơ chế transaction mà dự án dùng. Đặc biệt trong ứng dụng Spring Boot, cấu hình JPA chuẩn thường dựa vào transaction-scoped `EntityManager` thay vì yêu cầu ứng dụng tự cấu hình property này.

## 5. Context `jta`: Session gắn với transaction JTA

JTA (*Jakarta Transactions*) cung cấp cơ chế điều phối transaction trong môi trường có transaction manager. Với context kiểu `jta`, Hibernate xác định Session liên quan đến transaction JTA hiện tại và dùng cơ chế đồng bộ phù hợp để gắn việc flush/cleanup vào vòng đời transaction.

Luồng khái niệm:

```text
Transaction manager bắt đầu JTA transaction T1
    |
    +--> Service A -> getCurrentSession() -> Session S1
    |
    +--> Service B -> getCurrentSession() -> Session S1
    |
    +--> transaction commit / rollback
                         |
                         +--> flush/cleanup theo integration
                         +--> kết thúc phạm vi của S1
```

Trong giao dịch JTA đang hoạt động, các thành phần tham gia cùng transaction có thể chia sẻ current Session ứng với transaction ấy. Khi transaction kết thúc, Session hiện tại của transaction đó không còn được xem là phiên làm việc đang hoạt động cho transaction kế tiếp.

**Không được suy ra** rằng Hibernate “tự tạo JTA transaction” khi gọi `getCurrentSession()`. JTA transaction cần được bắt đầu bởi hạ tầng như container, interceptor `@Transactional` hoặc mã quản lý transaction tương ứng.

Một hàm nghiệp vụ chạy trong môi trường JTA được cấu hình phù hợp có thể dùng:

```java
import jakarta.transaction.Transactional;
import org.hibernate.Session;
import org.hibernate.SessionFactory;

public final class InventoryService {
    private final SessionFactory sessionFactory;

    public InventoryService(SessionFactory sessionFactory) {
        this.sessionFactory = sessionFactory;
    }

    @Transactional
    public void renameProduct(Long id, String name) {
        Session session = sessionFactory.getCurrentSession();
        Product product = session.find(Product.class, id);
        product.rename(name);
        // Transaction manager sẽ quyết định commit/rollback.
    }
}
```

Đoạn ví dụ giả định `@Transactional` được một container/framework hỗ trợ thực sự xử lý, và Hibernate `SessionFactory` tham gia vào JTA transaction ấy. Annotation đặt trên một object Java thuần tự khởi tạo bằng `new` **không tự bật JTA** nếu không có hạ tầng interception.

## 6. Context `thread`: Session theo luồng thực thi

Strategy `thread` sử dụng `ThreadLocalSessionContext` để liên kết current Session với luồng gọi đến `getCurrentSession()`.

Trong cấu hình Hibernate native thích hợp:

```properties
hibernate.current_session_context_class=thread
```

Một pattern đơn giản của Hibernate-managed session-per-transaction có thể là:

```java
Session session = sessionFactory.getCurrentSession();
Transaction tx = session.beginTransaction();

try {
    Product product = session.find(Product.class, productId);
    product.rename("Tên mới");
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

Với `ThreadLocalSessionContext`, Hibernate quản lý current Session theo thread và gắn xử lý vòng đời vào transaction theo cơ chế của context này. Cách xử lý đóng Session/cleanup cụ thể cần được hiểu theo version và tích hợp đang dùng. Ví dụ này minh họa **cách sử dụng trong môi trường chỉ định strategy `thread`**, không phải một quy tắc tổng quát rằng mọi lời gọi `getCurrentSession()` đều có quyền tự bắt đầu transaction và tự đóng Session.

### Vì sao thread không đồng nghĩa request?

Các server thường chạy trên thread pool:

```text
Thread #12 -> Request A -> kết thúc
Thread #12 -> Request B -> kết thúc
Thread #12 -> Request C -> kết thúc
```

Một thread có thể được tái sử dụng cho nhiều request. Ngược lại, một request có thể chuyển qua nhiều thread trong xử lý bất đồng bộ. Nếu tự viết ThreadLocal mà không dọn đúng thời điểm, dữ liệu phiên làm việc có thể rò rỉ sang request khác hoặc bị truy cập bởi thread không được phép.

Vì vậy:

- Đừng dùng `static ThreadLocal<Session>` tự phát chỉ để “có Session toàn cục theo thread”.
- Phải xác định lúc kết thúc transaction/unit of work và cơ chế cleanup.
- Với `CompletableFuture`, executor hoặc event loop, **đừng giả định** current Session theo thread tự đi theo công việc sang thread khác.
- Không sử dụng cùng một Session đồng thời trong nhiều thread, kể cả khi các thread thuộc một request.

Context `thread` là một chiến lược cụ thể của Hibernate, không phải tiêu chuẩn chung cho mọi ứng dụng web hoặc reactive.

## 7. Context `managed`: ứng dụng chủ động bind và unbind

Với `managed`, Hibernate không tùy ý lựa chọn một Session mới cho caller. Mã tích hợp chịu trách nhiệm **bind Session đang mở** vào context khi bước vào đơn vị công việc, rồi **unbind và đóng** sau khi kết thúc.

Cấu hình:

```properties
hibernate.current_session_context_class=managed
```

Interface/utility thường dùng là `org.hibernate.context.internal.ManagedSessionContext`. Mặc dù package chứa chữ `internal`, đây là một cách điều khiển binding được Hibernate cung cấp cho context `managed` ở những phiên bản có class này; việc phụ thuộc cần được giới hạn ở lớp bootstrap/infrastructure và kiểm tra tài liệu phiên bản cụ thể.

Ví dụ minh họa một boundary chạy đồng bộ trên một thread:

```java
import org.hibernate.Session;
import org.hibernate.SessionFactory;
import org.hibernate.Transaction;
import org.hibernate.context.internal.ManagedSessionContext;

public final class HibernateUnitOfWork {
    private final SessionFactory sessionFactory;

    public HibernateUnitOfWork(SessionFactory sessionFactory) {
        this.sessionFactory = sessionFactory;
    }

    public void execute(Runnable work) {
        Session session = sessionFactory.openSession();
        Transaction tx = null;

        try {
            ManagedSessionContext.bind(session);
            tx = session.beginTransaction();

            work.run(); // Các repository có thể dùng getCurrentSession().

            tx.commit();
        } catch (RuntimeException | Error ex) {
            if (tx != null && tx.isActive()) {
                try {
                    tx.rollback();
                } catch (RuntimeException rollbackFailure) {
                    ex.addSuppressed(rollbackFailure);
                }
            }
            throw ex;
        } finally {
            ManagedSessionContext.unbind(sessionFactory);
            session.close();
        }
    }
}
```

Repository dùng bên trong boundary:

```java
public final class ProductRepository {
    private final SessionFactory sessionFactory;

    public ProductRepository(SessionFactory sessionFactory) {
        this.sessionFactory = sessionFactory;
    }

    public Product get(Long id) {
        return sessionFactory.getCurrentSession().find(Product.class, id);
    }

    public void saveNew(Product product) {
        sessionFactory.getCurrentSession().persist(product);
    }
}
```

Và cách gọi:

```java
unitOfWork.execute(() -> {
    Product product = repository.get(42L);
    product.rename("Máy tính xách tay");
    // Không cần truyền Session qua từng phương thức.
});
```

Ý nghĩa của ví dụ:

1. `execute` là **chủ sở hữu vòng đời**: mở Session, bind, bắt đầu transaction, quyết định commit/rollback, unbind, đóng.
2. Repository chỉ lấy Session hiện hành để truy vấn và thay đổi entity; nó không được tự đóng Session.
3. Vì `managed` không tự xây dựng transaction, boundary phải chịu trách nhiệm điều phối transaction.
4. Nếu gọi repository ngoài `execute` hoặc sau `unbind`, việc lấy current Session có thể thất bại.
5. Ví dụ dùng callback đồng bộ. Không dùng chung một Session này cho nhiều tác vụ chạy song song.

Một lưu ý kiến trúc: `ManagedSessionContext` là lựa chọn tích hợp thủ công để hiểu hoặc xây dựng boundary Hibernate native. Ứng dụng đã có Spring/JTA thường nên dùng transaction manager của framework, tránh triển khai song song hai cơ chế quản lý Session mà không có thiết kế rõ.

### Khi nào cần lưu ý nested unit of work?

Nếu `execute` được gọi lồng nhau trên cùng một thread, boundary bên trong có thể bind Session khác, khiến logic nghiệp vụ bên ngoài không còn sử dụng Session như kỳ vọng. Ví dụ trình bày giả định **không lồng boundary**. Hệ thống thực tế phải quy định rõ chính sách: tham gia transaction hiện tại, mở transaction mới bằng cơ chế của framework, hay từ chối gọi lồng. Đây là lý do transaction manager có sẵn thường phù hợp hơn việc tự viết một abstraction quá đơn giản.

## 8. Session hiện tại trong Spring và Jakarta Persistence

Nhiều dự án dùng Spring Data JPA hoặc Spring Boot với Hibernate làm provider. Trong cấu hình JPA thông dụng, API được ứng dụng gọi trực tiếp là **`EntityManager`**, được Spring quản lý liên quan đến transaction và thực thể persistence context.

Ví dụ service với Spring:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductService {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void renameProduct(Long productId, String newName) {
        Product product = entityManager.find(Product.class, productId);
        product.rename(newName);
    }
}
```

Trong mô hình này:

- `@Transactional` tạo hoặc tham gia một transaction theo transaction manager được cấu hình.
- `@PersistenceContext` cho phép sử dụng EntityManager gắn với ngữ cảnh persistence do Spring quản lý.
- Các thay đổi entity managed được flush theo transaction.
- Service không cần gọi `SessionFactory.getCurrentSession()` và cũng không tự `close()` EntityManager do container/framework quản lý.

Nếu cần native Hibernate API từ `EntityManager`:

```java
import org.hibernate.Session;

Session hibernateSession = entityManager.unwrap(Session.class);
```

Đây là cách truy cập `Session` tương ứng trong môi trường Hibernate provider. Nó không yêu cầu tự triển khai `ThreadLocal` hoặc gọi `ManagedSessionContext.bind`.

### Có thể dùng `SessionFactory.getCurrentSession()` trong Spring không?

Có, **khi SessionFactory và transaction manager được tích hợp theo cơ chế hỗ trợ current Session tương ứng**. Ví dụ các cấu hình Spring Hibernate native có thể tổ chức Session theo transaction. Tuy nhiên, không nên suy luận rằng bất kỳ bean `SessionFactory` nào được lấy từ JPA `EntityManagerFactory` cũng có thể gọi `getCurrentSession()` mà không cần cấu hình/tích hợp bổ sung.

Khi ứng dụng chủ yếu dùng Spring Data JPA, sử dụng transaction-scoped `EntityManager` là ranh giới dễ hiểu hơn. Khi ứng dụng chọn Spring Hibernate native, hãy cấu hình transaction manager và current-session context của Hibernate/Spring tương ứng, thay vì tự kết hợp hai vòng đời.

### Lưu ý về proxy và `@Transactional`

Spring thường áp dụng transaction thông qua AOP proxy. Một phương thức được gọi trực tiếp từ phương thức khác trong **cùng object** (*self-invocation*) có thể không đi qua proxy transaction. Trong trường hợp đó, đặt `@Transactional` mà không có transaction thực sự có thể khiến code truy cập Session sai giả định. Tương tự, phương thức chạy bằng `new Thread(...)` hoặc executor khác không tự thừa hưởng transaction của thread gọi.

## 9. Quan hệ giữa Session hiện tại, transaction và JDBC connection

Ba khái niệm thường bị nhập làm một:

```text
Ngữ cảnh thực thi
    |
    v
Current Session
    |
    +--> Persistence context (managed entities, dirty checking)
    |
    +--> tham gia transaction khi được cấu hình/bắt đầu
                    |
                    v
             JDBC connection(s)
                    |
                    v
                 Database
```

Session **không nhất thiết giữ một JDBC connection suốt từ lúc mở đến lúc đóng**. Hibernate có thể trì hoãn lấy connection cho đến khi cần SQL và có những chiến lược release connection phụ thuộc cấu hình và transaction. Bởi vậy:

- “Đang có Session” không đồng nghĩa “đã mở connection vật lý”.
- “Đang có Session” không đồng nghĩa “đã bắt đầu transaction”.
- “Đã gọi `flush()`” không đồng nghĩa “đã `commit()`”.
- Một EntityManager/Session khác vẫn có persistence context riêng, dù kết nối tới cùng database.

Giao dịch vẫn cần thiết để bảo đảm tính nguyên tử khi cập nhật nhiều entity và kiểm soát việc ghi dữ liệu. Cố gắng dùng một Session quá lâu có thể khiến persistence context giữ nhiều entity, tăng bộ nhớ và làm việc flush tốn kém.

### Ví dụ cùng transaction, nhiều repository

```text
@Transactional placeOrder()
    |
    +--> customerRepository.findById(...) --\
    |                                      |
    +--> orderRepository.persist(...) -----+--> Session/Persistence context
    |                                      |    thuộc transaction hiện tại
    +--> stockRepository.decrease(...) ----/
    |
    +--> commit hoặc rollback
```

Nếu các repository dùng cùng cơ chế persistence context đã được transaction manager tích hợp, chúng có thể làm việc trong cùng transaction và persistence context. Nếu repository A tự `openSession()` độc lập, nó có thể tạo Session khác và không tự động tham gia cùng mô hình transaction mong muốn.

## 10. Ai chịu trách nhiệm đóng Session hiện tại?

**Quy tắc quan trọng nhất là xác định owner của Session trước khi viết `close()`.**

| Cách lấy Session | Owner thường gặp | Đóng khi nào? |
|---|---|---|
| `openSession()` do ứng dụng gọi | Chính code mở Session | Trong `finally` hoặc `try-with-resources` sau khi hoàn tất unit of work |
| `getCurrentSession()` với JTA | Hibernate/transaction integration | Theo lifecycle transaction do integration quản lý |
| `getCurrentSession()` với `thread` | Hibernate context cùng transaction lifecycle | Theo cơ chế của strategy; không tự đóng từ repository |
| `getCurrentSession()` với `managed` | Code/framework đã bind Session | Unbind và close tại boundary tương ứng |
| `@PersistenceContext EntityManager` trong Spring/Jakarta EE | Framework/container | Không tự đóng trong business service |

Không nên đặt mã sau trong repository khi Session thuộc framework:

```java
// Sai trong mô hình current Session do framework quản lý:
try (Session session = sessionFactory.getCurrentSession()) {
    return session.find(Product.class, id);
}
```

Khi block kết thúc, `close()` có thể đóng Session mà những repository khác trong cùng transaction đang cần. Thay vào đó:

```java
// Tại repository, chỉ sử dụng current Session:
Session session = sessionFactory.getCurrentSession();
return session.find(Product.class, id);
```

**Bên mở hoặc bind Session** chịu trách nhiệm hoàn thành vòng đời tại boundary thích hợp; repository không được giành quyền sở hữu tài nguyên của toàn transaction.

## 11. Ngữ cảnh thực thi khi có async, thread pool và reactive

Rất nhiều lỗi do giả định sai rằng “current” nghĩa là có thể dùng ở mọi thời điểm.

### 11.1. Chuyển sang thread khác

Ví dụ:

```java
@Transactional
public void processProduct(Long id) {
    Product product = entityManager.find(Product.class, id);

    CompletableFuture.runAsync(() -> {
        // Không sử dụng lại entityManager / Session hiện tại tại đây.
        // Transaction của thread gọi không tự chuyển sang worker thread.
    });
}
```

Trong hạ tầng thông thường dùng transaction context theo thread, task bất đồng bộ chạy trên thread khác **không tự nhận được Session/transaction** của caller. Kể cả khi ứng dụng chủ động truyền Session vào callback, Session không được thiết kế cho truy cập đồng thời.

Giải pháp thường là để tác vụ async **tạo transaction và persistence context của riêng nó** thông qua transaction manager ở boundary của tác vụ. Truyền ID hoặc dữ liệu immutable cần thiết thay vì truyền Session hoặc entity managed đang có nhiều lazy association.

### 11.2. Luồng HTTP request không phải lifecycle mặc định của Session

Một request có thể gọi nhiều service nhưng một transaction thường chỉ bao phủ một phần request. Session được quản lý theo transaction nên có thể kết thúc trước lúc serialize response. Nếu serializer cố truy cập quan hệ `LAZY` chưa nạp sau đó, ứng dụng có thể gặp `LazyInitializationException`.

Giải pháp là quyết định dữ liệu cần trả **ngay trong transaction**, ví dụ fetch join thích hợp hoặc projection DTO. Mở rộng Session đến cuối request bằng Open Session in View (OSIV) là một lựa chọn có đánh đổi, không phải cách tự động bảo đảm cấu trúc truy vấn hoặc transaction đúng.

### 11.3. Hibernate ORM truyền thống khác Hibernate Reactive

Hibernate ORM thông thường dựa trên API blocking và JDBC. Hibernate Reactive dùng cơ chế bất đồng bộ/non-blocking và cách gắn phiên làm việc với execution context phù hợp reactive. Không nên áp dụng nguyên xi `ThreadLocalSessionContext`, cách gọi blocking Session hoặc mô hình `@Transactional` truyền thống cho pipeline reactive.

Điều cần nhớ là: **cơ chế context phải khớp với mô hình concurrency của runtime**.

## 12. Các lỗi thường gặp và cách xác định nguyên nhân

### 12.1. `No CurrentSessionContext configured`

Triệu chứng điển hình: gọi `sessionFactory.getCurrentSession()` nhưng Hibernate không có context strategy được thiết lập phù hợp.

Nguyên nhân:
- Dùng Hibernate native mà chưa cấu hình `hibernate.current_session_context_class`.
- Đã chuyển cơ chế transaction/bootstrap nhưng chưa cập nhật cách lấy Session.
- Dùng `getCurrentSession()` ở nơi chỉ có Session tạo bởi `openSession()` mà chưa bind.

Hướng xử lý: quyết định ownership/session pattern. Nếu caller mở/đóng Session thủ công thì dùng `openSession()`. Nếu cần current Session, chọn và cấu hình context thích hợp, đồng thời thiết lập transaction integration tương ứng.

### 12.2. `No session currently bound to execution context`

Thường gặp khi dùng context `managed` nhưng code chưa bind Session hoặc đã unbind trước khi repository được gọi. Cũng có thể do gọi repository từ worker thread khác với thread đã bind.

Hướng xử lý: đặt boundary rõ ràng, kiểm tra nơi mở/bind/transaction và nơi unbind/close. Tránh lén mở một Session mới trong repository để che lỗi thiếu context, vì việc đó tạo unit of work khác ngoài dự kiến.

### 12.3. `Session is closed` hoặc lỗi lazy loading

Có thể do:
- Một repository tự đóng current Session.
- Code giữ entity rồi truy cập lazy association sau khi Session kết thúc.
- Đơn vị công việc bất đồng bộ sử dụng Session hoặc entity sau lifecycle ban đầu.

Hướng xử lý: trả DTO đã có đủ dữ liệu, fetch đúng quan hệ trong transaction và để owner quản lý Session.

### 12.4. Transaction không tồn tại khi ghi dữ liệu

Có current Session nhưng chưa có transaction phù hợp; thao tác cập nhật có thể bị lỗi hoặc không mang semantics mà ứng dụng kỳ vọng. Các thao tác ghi quan trọng nên được đặt trong transaction rõ ràng.

Kiểm tra transaction manager và interception `@Transactional`, không chỉ kiểm tra `session.isOpen()`.

### 12.5. Rò rỉ connection hoặc persistence context giữ quá nhiều entity

Nếu sử dụng `openSession()` mà bỏ `close()`, hoặc dùng `managed` nhưng không unbind/close trong `finally`, Session có thể tồn tại lâu hơn cần thiết. Dữ liệu managed được giữ trong persistence context cũng có thể tích tụ khi xử lý batch quá lớn.

Hướng xử lý: boundary đóng tài nguyên đáng tin cậy, transaction ngắn phù hợp; đối với batch lớn, phân lô và dùng cơ chế flush/clear thích hợp theo từng tác vụ.

## 13. Cách lựa chọn cơ chế cho từng kiến trúc

| Môi trường | Hướng dùng Session thường hợp lý |
|---|---|
| Ứng dụng đơn giản dùng Hibernate native, tác vụ độc lập | `openSession()` + transaction + `close()` do caller quản lý |
| Hibernate native muốn nhiều repository chia sẻ unit of work đồng bộ | Current-session context được cấu hình, với boundary transaction rõ ràng |
| Hạ tầng Jakarta EE/JTA | Transaction-scoped persistence và context tích hợp JTA |
| Spring Boot + Spring Data JPA | `@Transactional` và `EntityManager` do Spring quản lý |
| Spring + Hibernate native được cấu hình riêng | Dùng `getCurrentSession()` khi tích hợp SessionFactory/transaction manager hỗ trợ nó |
| Worker async hoặc batch chạy song song | Mỗi task có transaction và Session riêng, không chia sẻ Session giữa các worker |
| Ứng dụng reactive | Dùng API/session context được hỗ trợ bởi stack reactive tương ứng |

### Khi nào nên truyền Session như tham số?

Không phải mọi ứng dụng đều cần `getCurrentSession()`. Với những module nhỏ hoặc mã chuyên xử lý một truy vấn, một phương thức nhận trực tiếp `Session` là lựa chọn minh bạch:

```java
public Product findProduct(Session session, Long id) {
    return session.find(Product.class, id);
}
```

Caller là owner của Session và transaction; repository không phải phụ thuộc vào current-session context. Cách này phù hợp khi muốn nhìn rõ ranh giới tài nguyên trong chữ ký hàm.

Ngược lại, trong ứng dụng nhiều repository, việc truyền Session qua mọi lớp có thể gây bất tiện. Khi transaction manager và context đã quản lý đúng, `getCurrentSession()` hoặc injected `EntityManager` giúp các thành phần tham gia unit of work thống nhất.

Không có một cách bắt buộc cho mọi hệ thống. Điều quan trọng là **nhất quán về ownership và lifecycle**.

## 14. Tình huống tổng hợp: cùng một nghiệp vụ, hai kiểu quản lý

Giả sử thao tác *đổi tên sản phẩm* gồm:

1. Bắt đầu transaction.
2. Tìm sản phẩm.
3. Đổi thuộc tính.
4. Commit; rollback nếu lỗi.
5. Đóng hoặc giải phóng tài nguyên.

**Cách A: code tự quản lý Session**

```java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();
    try {
        Product product = session.find(Product.class, id);
        product.rename(newName);
        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
}
```

Chính block này điều khiển transaction và Session; không có khái niệm “current” bên ngoài nó.

**Cách B: framework quản lý transaction**

```java
@Transactional
public void renameProduct(Long id, String newName) {
    Product product = entityManager.find(Product.class, id);
    product.rename(newName);
}
```

Ở cách B, hạ tầng Spring/JTA hợp lệ bao quanh method và cung cấp persistence context. Code nghiệp vụ không bắt đầu transaction, commit hay đóng EntityManager thủ công.

Hai cách có cùng mục tiêu nghiệp vụ, nhưng **quyền sở hữu tài nguyên khác nhau**. Trộn lẫn hai mô hình mà không phân định rõ có thể gây ra lỗi Session bị đóng sớm, transaction không đồng bộ hoặc hai persistence context cho một nghiệp vụ.

## 15. Ghi nhớ

- **`SessionFactory`** chia sẻ được; **`Session`** có vòng đời ngắn và không an toàn cho truy cập đồng thời giữa các thread.
- **`openSession()`** tạo Session mới và đặt trách nhiệm đóng lên bên mở.
- **`getCurrentSession()`** lấy Session theo `CurrentSessionContext` được cấu hình; “current” mang nghĩa *thuộc ngữ cảnh*, không phải một biến toàn cục.
- Các context `jta`, `thread`, `managed` có cách xác định Session và trách nhiệm lifecycle khác nhau.
- **Current Session, persistence context, transaction và JDBC connection là các khái niệm có quan hệ nhưng không đồng nghĩa.**
- Repository sử dụng Session do framework/transaction manager quản lý thì không tự `close()`.
- Khi có async, thread pool hoặc reactive, phải xét lại ngữ cảnh thực thi thay vì giả định Session được truyền ngầm.
- Với Spring Data JPA thông thường, `@Transactional` cùng injected `EntityManager` là cách tích hợp dễ hiểu; chỉ dùng Hibernate native context khi kiến trúc thực sự cần.

Điểm cốt lõi: **Session hiện tại là Session được xác định bởi một quy tắc liên kết với ngữ cảnh thực thi**. Muốn dùng nó an toàn, ứng dụng phải hiểu ngữ cảnh đó là transaction, thread hay binding thủ công; ai tạo Session, ai bắt đầu transaction và ai có trách nhiệm dọn tài nguyên khi công việc kết thúc.

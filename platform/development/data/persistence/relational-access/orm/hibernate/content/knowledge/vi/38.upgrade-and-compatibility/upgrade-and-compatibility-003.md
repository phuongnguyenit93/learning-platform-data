# Phân biệt API công khai với SPI hoặc API nội bộ dễ thay đổi

## 1. Vì sao phân biệt API lại quan trọng khi dùng Hibernate?

Hibernate ORM cung cấp nhiều lớp và interface để ứng dụng làm việc với persistence context, transaction, mapping, SQL generation, event, type system và JDBC. Nhìn từ code Java, nhiều class đều có thể import, nhiều method đều là `public`, và một số class nội bộ thậm chí còn có tên rất hấp dẫn như `SessionImpl`, `EntityPersister` hay `JdbcCoordinator`.

Tuy nhiên, **có thể gọi được một class không có nghĩa đó là một hợp đồng API mà ứng dụng nên phụ thuộc lâu dài**.

Khi nâng Hibernate từ một phiên bản lên phiên bản khác, ứng dụng có thể gặp:
- Compile error vì method hoặc class đã đổi package/đổi chữ ký.
- `NoSuchMethodError` hoặc `NoClassDefFoundError` khi runtime nạp binary được build với version khác.
- Thay đổi behavior dù code vẫn compile.
- Custom integration không còn hoạt động vì extension point đã thay đổi.
- Reflection thất bại vì field, constructor hoặc internal structure đã được refactor.
- Một tính năng từng dùng được nhưng chưa từng được cam kết là public contract bị loại bỏ.

Ví dụ, code sau phụ thuộc vào một implementation class:

~~~java
Session session = entityManager.unwrap(Session.class);

SessionImpl implementation = (SessionImpl) session;
// Truy cập implementation-specific state...
~~~

`SessionImpl` là chi tiết triển khai của Hibernate. Ứng dụng thường chỉ cần public `Session` contract:

~~~java
Session session = entityManager.unwrap(Session.class);
session.flush();
~~~

Cách thứ hai vẫn phụ thuộc Hibernate thay vì chỉ Jakarta Persistence, nhưng phụ thuộc vào một abstraction được Hibernate công bố như API.

Bài học thuộc chương **Nâng cấp và tương thích** trong module *Data Persistence Relational Access ORM Hibernate*. Mục tiêu là nhận diện mức cam kết của một API, chọn extension point phù hợp, và giảm chi phí khi nâng cấp.

### 1.1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Phân biệt API portable của Jakarta Persistence, Hibernate public API, SPI và internal implementation.
2. Hiểu vì sao package name, modifier `public` và việc class xuất hiện trong Javadoc chưa đủ để kết luận API ổn định.
3. Nhận biết các dấu hiệu như `@Incubating`, `@Internal`, `@Deprecated` và version-specific migration notes.
4. Chọn extension point công khai cho SQL inspection, events, interceptors, types và custom functions.
5. Tránh phụ thuộc vào internal classes, reflection và implementation details.
6. Đánh giá source, binary, behavioral, configuration và database compatibility.
7. Lập quy trình nâng cấp Hibernate có kiểm soát.
8. Thiết kế dependency và integration tests để phát hiện incompatibility sớm.

## 2. API, SPI và implementation là ba mức hợp đồng khác nhau

Các thuật ngữ này thường xuất hiện trong tài liệu framework, nhưng không phải lúc nào cũng được dùng thống nhất. Với Hibernate, có thể hiểu thực tế như sau.

### 2.1. API — Application Programming Interface

**API công khai** là những kiểu dữ liệu và operations mà thư viện chủ đích cung cấp cho consumer sử dụng. Nó định nghĩa cách ứng dụng gọi thư viện mà không cần biết implementation cụ thể.

Ví dụ Hibernate/JPA:
- `jakarta.persistence.EntityManager`
- `jakarta.persistence.EntityManagerFactory`
- `jakarta.persistence.Query`
- `org.hibernate.Session`
- `org.hibernate.SessionFactory`
- `org.hibernate.Hibernate`

Ứng dụng có thể gọi các contract này để persist/find/remove entities, chạy query, flush, clear hoặc kiểm tra lazy initialization.

API không nhất thiết portable giữa các ORM. `EntityManager` là Jakarta Persistence API; `Session` là Hibernate-specific public API. Cả hai đều có thể là API công khai, nhưng **phạm vi tương thích khác nhau**.

### 2.2. SPI — Service Provider Interface

SPI là contract được thiết kế để **provider hoặc extension implement**, hoặc để framework gọi ngược vào implementation do ứng dụng đăng ký.

Ví dụ theo Hibernate version và extension use case:
- `org.hibernate.integrator.spi.Integrator`
- Một số contracts trong `org.hibernate.boot.spi`
- Các extension contracts trong event, type hoặc service infrastructure.

SPI thường cần cho:
- Đăng ký event listeners.
- Tích hợp framework/module ngoài.
- Đóng góp custom types hoặc SQL functions.
- Can thiệp vào bootstrap metadata hoặc service lifecycle.

SPI có thể là extension point chính thức, nhưng mức ổn định **không nên mặc định bằng API cấp cao**. SPI thường gần internals hơn vì nó phải mô tả nhiều chi tiết mà framework cần để extension hoạt động.

Một số SPI được Hibernate hỗ trợ theo compatibility policy rõ ràng; một số khác có thể thay đổi theo major version hoặc mang annotation báo hiệu. Phải xem Javadoc, migration guide và trạng thái của từng contract.

### 2.3. Internal implementation

Internal implementation là class hoặc method phục vụ chính Hibernate thực thi công việc bên trong. Nó không được thiết kế làm hợp đồng cho ứng dụng bên ngoài.

Ví dụ thường gặp trong source tree/package:
- `org.hibernate.internal.*`
- `org.hibernate.engine.internal.*`
- `org.hibernate.boot.internal.*`
- Các implementation classes như `SessionImpl`, `SessionFactoryImpl`.
- Các lớp nội bộ điều phối persistence context, SQL AST, JDBC coordination hoặc entity persisters.

Một class nội bộ có thể:
- Có constructor public.
- Implement interface công khai.
- Có mặt trong Javadoc.
- Được một extension cũ sử dụng.
- Không thay đổi trong nhiều releases.

Những điều đó **không tự biến nó thành supported public API**.

### 2.4. Bảng so sánh

| Mức | Ai là consumer chính? | Mức phụ thuộc phù hợp | Rủi ro nâng cấp |
|---|---|---|---|
| Jakarta Persistence API | Ứng dụng Java dùng JPA | Rất phù hợp cho code cần portability | Theo spec/provider support |
| Hibernate public API | Ứng dụng chủ động dùng Hibernate | Phù hợp khi chấp nhận Hibernate-specific behavior | Theo Hibernate compatibility policy |
| Hibernate SPI | Extension/framework tích hợp với Hibernate | Dùng khi không có API cấp cao đáp ứng nhu cầu | Cần theo dõi version/migration kỹ |
| Internal implementation | Chính Hibernate | Tránh phụ thuộc trực tiếp trong application code | Cao; refactor nội bộ có thể phá code bất kỳ lúc nào |

### 2.5. Không có quy tắc “API = interface, SPI = class”

Một API có thể là class, interface, annotation hoặc enum. SPI cũng có thể là interface, abstract class, callback hoặc service contract.

Ví dụ:
- `Session` là interface public API.
- `Hibernate` là class tiện ích public API.
- `@SoftDelete` là annotation Hibernate-specific.
- `Integrator` là SPI interface.
- `SessionImpl` là implementation class.

Hãy xét **ý định và compatibility contract**, không chỉ cấu trúc Java.

## 3. Jakarta Persistence API và Hibernate public API

### 3.1. Jakarta Persistence API: lựa chọn cho portability

Các types thuộc namespace `jakarta.persistence` được định nghĩa bởi Jakarta Persistence specification.

Ví dụ:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.TypedQuery;
import jakarta.persistence.LockModeType;
import jakarta.persistence.Persistence;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.Version;
~~~

Một service dùng API portable:

~~~java
@Service
public class UserService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public User create(User user) {
        entityManager.persist(user);
        return user;
    }

    @Transactional(readOnly = true)
    public User find(Long id) {
        return entityManager.find(User.class, id);
    }
}
~~~

Code này có thể chạy với nhiều JPA providers nếu mapping và query chỉ dùng những features được provider hỗ trợ theo spec.

**Portable không có nghĩa tất cả provider thực thi giống hệt nhau về hiệu năng hoặc mọi extension đều có mặt.** Nhưng specification tạo một hợp đồng chung tốt hơn so với gọi trực tiếp implementation của Hibernate.

### 3.2. Hibernate public API: dùng khi cần khả năng đặc thù

Hibernate public API nằm trong namespace `org.hibernate` và các packages liên quan được công bố. Ví dụ:

~~~java
import org.hibernate.Session;
import org.hibernate.SessionFactory;
import org.hibernate.Hibernate;
~~~

Có thể unwrap từ JPA:

~~~java
Session session = entityManager.unwrap(Session.class);

session.flush();
boolean initialized = Hibernate.isInitialized(entity.getChildren());
~~~

Đây là lựa chọn hợp lý khi:
- Ứng dụng chọn Hibernate làm provider chính.
- Cần API không có trong Jakarta Persistence.
- Hibernate công bố contract phù hợp và có tài liệu/Javadoc.
- Đội ngũ chấp nhận coupling với Hibernate version.

Không cần né mọi `org.hibernate.*` imports. Vấn đề là **dùng đúng contract được hỗ trợ**, không phải cấm toàn bộ provider-specific API.

### 3.3. Hibernate annotations vẫn có thể là public API

Một số mapping features của Hibernate không thuộc Jakarta Persistence nhưng được cung cấp dưới dạng annotations/classes có tài liệu, ví dụ trong `org.hibernate.annotations`.

Ứng dụng có thể dùng chúng khi chấp nhận portability trade-off. Cần phân biệt:
- Hibernate-specific nhưng được công bố như API.
- Hibernate SPI dành cho extension.
- Internal implementation.
- Annotation/class được đánh dấu incubating/internal.

Tên package `org.hibernate.annotations` không bảo đảm mọi type trong đó có cùng mức compatibility. Kiểm tra từng annotation trong Javadoc của version đang dùng.

### 3.4. Portability và stability là hai câu hỏi riêng

| Câu hỏi | Ví dụ |
|---|---|
| Có portable giữa JPA providers không? | `EntityManager` và JPQL theo spec |
| Có phải Hibernate public API không? | `Session` |
| Có phải SPI không? | `Integrator` |
| Có bị đánh dấu experimental/internal không? | Type có `@Incubating` hoặc `@Internal` |
| Có ổn định qua major versions không? | Phải xem contract/version policy cụ thể |

Một API Hibernate-specific vẫn có thể ổn định trong phạm vi Hibernate. Một feature thuộc specification cũng có thể thay đổi khi nâng Jakarta Persistence major version. Không đồng nhất portability với stability.

## 4. Nhận diện package và type có mức rủi ro khác nhau

### 4.1. Package root org.hibernate

Nhiều public API quan trọng nằm trực tiếp dưới `org.hibernate`, chẳng hạn `Session`, `SessionFactory`, `Hibernate`, `Interceptor` và `Transaction`.

Đây thường là điểm bắt đầu tốt khi cần Hibernate-specific API.

Tuy nhiên, **không dùng quy tắc “nằm ở root thì chắc chắn stable”**. Annotation trạng thái, Javadoc và version-specific documentation vẫn quan trọng.

### 4.2. Package org.hibernate.boot

Các public bootstrap APIs có thể giúp xây dựng metadata, registry và SessionFactory.

Ví dụ:
- `org.hibernate.boot.MetadataSources`
- `org.hibernate.boot.Metadata`
- `org.hibernate.boot.registry.StandardServiceRegistryBuilder`

Một ứng dụng tự bootstrap Hibernate có thể dùng chúng theo hướng dẫn chính thức. Các package con `*.spi` hoặc `*.internal` phải được xem xét riêng.

### 4.3. Package org.hibernate.boot.spi

Đây là nơi có các contracts dành cho service providers/integrations. Một số extension points là SPI có chủ đích; không nên hiểu chữ `spi` là “không bao giờ được dùng”.

Nhưng khi phụ thuộc:
- Xác định vì sao cần SPI thay vì public API cấp cao.
- Đọc Javadoc và migration notes của type.
- Kiểm tra annotation stability.
- Giữ integration tests cho bootstrap.
- Đánh giá chi phí port khi Hibernate major version thay đổi.

### 4.4. Package org.hibernate.engine.spi

Một số contracts quan trọng cho advanced integrations xuất hiện ở package này, nhưng đây cũng là vùng gần engine internals.

Ví dụ type như `SharedSessionContractImplementor`, `SessionFactoryImplementor`, `PersistenceContext` hoặc `EntityEntry` thường xuất hiện trong integrations nâng cao và Hibernate internals.

Không nên chỉ thấy `public interface` rồi dùng nó trong mọi service/repository. Hãy hỏi:
- Đây là extension contract được docs yêu cầu hay chỉ là type nội bộ bị lộ?
- Có API cấp cao hơn không?
- Có bị `@Incubating`/`@Internal` đánh dấu không?
- Hibernate có cam kết compatibility cho use case này không?

### 4.5. Package có chữ internal

Các package như `org.hibernate.internal`, `org.hibernate.engine.internal`, `org.hibernate.boot.internal` là tín hiệu rất rõ để không phụ thuộc trực tiếp.

Ví dụ:

~~~java
// Không nên xây application code dựa trên implementation này:
import org.hibernate.internal.SessionImpl;
~~~

Thay bằng public contract:

~~~java
Session session = entityManager.unwrap(Session.class);
~~~

### 4.6. Một số package có thể gây nhầm

| Package/type | Nhận định ban đầu | Việc cần làm |
|---|---|---|
| `jakarta.persistence.*` | Specification API | Theo Jakarta Persistence version/provider support |
| `org.hibernate.Session` | Hibernate public API | Đọc Javadoc theo Hibernate version |
| `org.hibernate.annotations.*` | Hibernate-specific extension API | Kiểm tra từng type/annotation |
| `org.hibernate.boot.*` | Bootstrap API và types liên quan | Phân biệt package chính với `.spi`/`.internal` |
| `org.hibernate.*.spi` | SPI/extension contracts | Đọc compatibility notes và mức ổn định |
| `org.hibernate.engine.spi.*` | Advanced engine-facing contracts | Dùng thận trọng, tìm API cấp cao hơn |
| `org.hibernate.*.internal.*` | Implementation detail | Tránh dependency |
| `org.hibernate.testing.*` | Testing infrastructure của Hibernate | Không mặc định là application runtime API |

Đây là heuristic để bắt đầu điều tra, không thay thế tài liệu của từng class.

## 5. Modifier public không đồng nghĩa public contract

Java compiler chỉ kiểm tra accessibility ở mức ngôn ngữ. Nó không biết một class có được Hibernate cam kết giữ ổn định qua releases hay không.

Ví dụ:

~~~java
public class SessionImpl implements Session {
    // Implementation details...
}
~~~

Class có thể public để:
- Cho framework/module khác trong cùng distribution truy cập.
- Hỗ trợ serialization/reflection nội bộ.
- Làm implementation của một interface.
- Phục vụ integration đặc thù.

Điều đó không đồng nghĩa ứng dụng bên ngoài nên instantiate hoặc cast sang class này.

### 5.1. Vì sao implementation class cần public?

Một framework lớn có nhiều modules, package boundaries và service loading. Java visibility không phải cơ chế duy nhất để biểu đạt support contract. Một type có thể phải public về kỹ thuật nhưng vẫn là implementation detail theo documentation.

### 5.2. Interface cũng không tự động stable

Một interface trong `*.spi` có thể được implement bởi ứng dụng, nhưng Hibernate vẫn có thể điều chỉnh SPI theo version hoặc annotation status.

Không suy luận:
- interface ⇒ API ổn định.
- public ⇒ supported.
- final ⇒ stable.
- Có Javadoc ⇒ public compatibility guarantee.

Hãy đọc contract và version notes.

## 6. Annotation trạng thái và tài liệu cần đọc

### 6.1. @Incubating

Hibernate dùng `@Incubating` để đánh dấu một API/feature đang trong giai đoạn phát triển và có thể thay đổi. Đây là tín hiệu cần thận trọng hơn API đã ổn định.

Khi gặp type hoặc method có annotation này:
- Kiểm tra Javadoc ghi chú về compatibility.
- Xác định release đầu tiên giới thiệu feature.
- Xem migration guide/release notes ở các version tiếp theo.
- Tránh expose type đó qua public interfaces của application nếu chưa cần.
- Viết test riêng cho integration dựa vào feature.
- Ước lượng chi phí thay thế trước khi đưa vào nền tảng dùng lâu dài.

Không mặc định `@Incubating` có nghĩa “không dùng được”. Nó có nghĩa **không nên dựa vào kỳ vọng stability giống API đã được hỗ trợ ổn định**.

### 6.2. @Internal

Nếu một type/method được đánh dấu `@Internal`, đó là chỉ dẫn mạnh rằng nó dành cho Hibernate internals hoặc không phải contract cho application code.

Ví dụ minh họa:

~~~java
// Pseudocode: type/method được tài liệu đánh dấu internal.
@Internal
public class SomeEngineHelper {
}
~~~

Không xây extension bằng cách truy cập nó chỉ vì compiler cho phép. Tìm public API/SPI thay thế hoặc hỏi maintainers nếu use case thật sự cần hook nội bộ.

### 6.3. @Deprecated

`@Deprecated` cho biết API đã bị khuyến cáo không dùng nữa. Nhưng cần đọc:
- Replacement API được đề xuất là gì?
- Deprecation xuất hiện từ version nào?
- Có `forRemoval=true` không?
- Removal dự kiến hoặc thực tế ở version nào?
- Có khác biệt behavior khi chuyển sang replacement không?

Ví dụ Java:

~~~java
@Deprecated(since = "6.x", forRemoval = true)
public void oldOperation() {
}
~~~

Đây chỉ là ví dụ minh họa cách Java biểu diễn deprecation, không khẳng định một Hibernate method cụ thể có annotation/version như vậy.

**Không xóa code deprecated một cách máy móc** nếu replacement có semantics khác. Chuyển đổi phải có test behavior.

### 6.4. Javadoc và migration guide quan trọng hơn tên gọi

Khi quyết định phụ thuộc một type:
1. Mở Javadoc của đúng Hibernate version.
2. Đọc class-level note và method-level note.
3. Xem package summary.
4. Kiểm tra annotations.
5. Tìm migration guide từ version hiện tại tới version mục tiêu.
6. Xem release notes có thay đổi hoặc deprecate feature không.
7. Kiểm tra examples chính thức dùng API đó như thế nào.

Đừng chỉ đọc trang current rồi áp dụng cho project đang dùng Hibernate cũ.

### 6.5. Incubating và deprecated có thể cùng tồn tại

Một API replacement mới có thể đang incubating trong khi API cũ đã deprecated. Khi đó phải đánh giá trade-off:
- Dùng deprecated API cũ tạm thời với kế hoạch migration.
- Dùng incubating API mới và chấp nhận thay đổi ở release sau.
- Chọn extension point khác ổn định hơn.
- Chuyển logic lên tầng application để tránh phụ thuộc cả hai.

Ghi quyết định vào code/architecture note để lần nâng cấp sau biết vì sao dependency tồn tại.
+
## 7. Chọn extension point công khai thay vì hook nội bộ

Khi cần tùy biến Hibernate, bước đầu tiên là xác định **sự kiện hoặc behavior cần mở rộng**. Sau đó tìm extension point được tài liệu hỗ trợ.

### 7.1. Lifecycle callbacks của Jakarta Persistence

Nếu cần chạy logic quanh lifecycle entity đơn giản, JPA callbacks thường portable:

~~~java
@Entity
@EntityListeners(UserAuditListener.class)
public class User {

    @Id
    private Long id;

    @PrePersist
    void beforeInsert() {
        // Chuẩn bị state đơn giản trước persist.
    }

    @PreUpdate
    void beforeUpdate() {
        // Chuẩn bị state đơn giản trước update.
    }
}
~~~

Hoặc listener class:

~~~java
public class UserAuditListener {

    @PrePersist
    public void beforeInsert(User user) {
        user.setCreatedAt(Instant.now());
    }
}
~~~

Callbacks không phù hợp cho mọi side effect:
- Không nên gửi email/HTTP request trực tiếp trong callback.
- Bulk JPQL/native DML không gọi callbacks cho từng entity như entity lifecycle.
- Thứ tự/cascade semantics cần theo JPA specification.
- Nếu cần after-commit event, dùng transaction-aware event/outbox pattern.

### 7.2. Hibernate Interceptor

`org.hibernate.Interceptor` là Hibernate-specific extension API cho một số callbacks/inspection liên quan entity state và lifecycle.

Ví dụ khái niệm:

~~~java
public class AuditInterceptor implements Interceptor {

    @Override
    public boolean onFlushDirty(
            Object entity,
            Object id,
            Object[] currentState,
            Object[] previousState,
            String[] propertyNames,
            Type[] types) {
        // Inspect/change state theo contract của version.
        return false;
    }
}
~~~

Đây là code minh họa, không phải mẫu copy nguyên trạng cho mọi Hibernate version: signatures và method overloads có thể thay đổi. Đọc Javadoc đúng version trước khi implement.

Interceptor hữu ích khi logic cần quan sát nhiều entity operations ở tầng Hibernate, nhưng:
- Là Hibernate-specific.
- Có thể tác động tới nhiều entities trong SessionFactory/session scope tùy registration.
- Cần hiểu thread safety và state sharing.
- Không phải cách thay thế DB constraints.
- Không được giả định chạy cho bulk/native DML như entity dirty checking.

### 7.3. Event system và Integrator SPI

Hibernate có event infrastructure để đăng ký listeners cho các operations như load, persist, delete, flush hoặc collection events.

Ở advanced integration, `Integrator` SPI có thể dùng trong bootstrap để đăng ký listener/service. Đây là extension point dành cho tích hợp framework/module, không phải lời mời gọi truy cập mọi internal registry.

Khi sử dụng:
- Xác nhận event type/listener contract trong Hibernate version.
- Kiểm tra listener ordering và registration.
- Không dựa vào undocumented invocation order.
- Không giữ mutable request state trong listener singleton.
- Kiểm tra bulk DML/native SQL có bypass event path hay không.
- Viết integration tests cho cả lifecycle và transaction behavior.

Nếu use case chỉ là `@PrePersist` hoặc application domain event, đừng kéo cả SPI event system vào khi không cần.

### 7.4. StatementInspector cho SQL inspection

`org.hibernate.resource.jdbc.spi.StatementInspector` là một extension contract để inspect SQL statement string do Hibernate chuẩn bị.

~~~java
import org.hibernate.resource.jdbc.spi.StatementInspector;

public class SqlTaggingInspector implements StatementInspector {

    @Override
    public String inspect(String sql) {
        // Có thể ghi nhận fingerprint hoặc trả SQL đã điều chỉnh
        // theo use case được hỗ trợ.
        return sql;
    }
}
~~~

Có thể đăng ký qua cấu hình Hibernate tương ứng, ví dụ:

~~~properties
hibernate.session_factory.statement_inspector=com.example.SqlTaggingInspector
~~~

Lưu ý:
- Inspector nhận SQL text, không phải toàn bộ bound parameter values.
- Không dùng nó làm security firewall hoặc row-level authorization.
- Không giả định nó đếm network round trips.
- Cần giữ implementation thread-safe nếu instance được chia sẻ.
- Tránh ghi raw SQL có literals/PII hoặc sửa SQL bằng regex không an toàn.

### 7.5. TypeContributor/UserType cho custom type mapping

Khi cần mapping kiểu dữ liệu đặc thù, Hibernate có các type extension contracts như `UserType` hoặc `TypeContributor` tùy version.

Trước khi implement:
- Kiểm tra Hibernate đã có built-in mapping phù hợp chưa.
- Xem Jakarta Persistence `AttributeConverter` có đủ không.
- Đọc type system/migration notes đúng major version.
- Test JDBC binding, extraction, null handling, equality/hashCode và schema validation.
- Kiểm tra behavior với native queries, cache và dirty checking.

Nếu chỉ chuyển một value object sang/về scalar database column, `AttributeConverter` thường là lựa chọn đơn giản và portable hơn custom Hibernate type.

### 7.6. FunctionContributor cho SQL functions

Khi cần đóng góp SQL function cho HQL/JPQL translation, Hibernate 6 có extension contracts dành cho function registration như `FunctionContributor` trong các version hỗ trợ.

Trước khi dùng:
- Kiểm tra function có sẵn trong Dialect chưa.
- Xác định function portable hay DB-specific.
- Đăng ký qua cơ chế bootstrap/ServiceLoader được docs của version hướng dẫn.
- Test generated SQL trên database thật.
- Theo dõi API changes giữa Hibernate major versions.

Không can thiệp internal SQL AST/function registry bằng reflection nếu có contributor contract phù hợp.

### 7.7. Bảng chọn extension

| Nhu cầu | Lựa chọn nên xem trước |
|---|---|
| Entity callback portable | JPA lifecycle callbacks / `EntityListener` |
| Domain side effect sau commit | Spring transaction event hoặc transactional outbox |
| SQL inspection/tagging | `StatementInspector` |
| Entity state callbacks ở Hibernate | `Interceptor` |
| Hibernate event listener integration | Event system / `Integrator` SPI |
| Simple value conversion | JPA `AttributeConverter` |
| Custom Hibernate JDBC type | Public type extension contracts của version |
| Custom HQL SQL function | `FunctionContributor` hoặc Dialect API được docs hỗ trợ |
| Đọc state nội bộ của Session | Tìm public Session/JPA API trước; chỉ dùng SPI khi integration thực sự yêu cầu |
| Thay đổi SQL executor nội bộ | Không phụ thuộc internal; xem extension chính thức hoặc thiết kế lại |

## 8. Ví dụ: thay internal cast bằng public contract

### 8.1. Đọc entity state

Không nên:

~~~java
SessionImpl session = (SessionImpl) entityManager.unwrap(Session.class);
PersistenceContext context = session.getPersistenceContext();
// Dựa vào internal entity entries...
~~~

Nên:
- Dùng JPA `PersistenceUnitUtil.isLoaded(...)` khi chỉ cần kiểm tra load state theo JPA.
- Dùng `Hibernate.isInitialized(...)` khi cần Hibernate lazy-state check.
- Dùng `EntityManager.contains(entity)` nếu câu hỏi là entity có đang managed không.
- Dùng `EntityManager.find/getReference` theo contract cần thiết.
- Dùng query/projection thay vì đọc internal persistence context.

### 8.2. Kiểm tra entity managed

~~~java
boolean managed = entityManager.contains(user);
~~~

Không cần lấy internal `EntityEntry` chỉ để trả lời câu hỏi đơn giản này.

### 8.3. Flush và clear

Dùng contract:

~~~java
entityManager.flush();
entityManager.clear();
~~~

hoặc Hibernate `Session` public API khi cần provider-specific behavior. Không gọi trực tiếp `ActionQueue` hoặc persistence context implementation để ép Hibernate chạy pending operations.

### 8.4. Lazy initialization

Dùng:

~~~java
boolean loaded = Persistence.getPersistenceUtil()
    .isLoaded(order, "items");
~~~

hoặc:

~~~java
boolean loaded = Hibernate.isInitialized(order.getItems());
~~~

Không đọc internal proxy initializer fields bằng reflection. Implementation proxy/enhancement có thể đổi mà không thay đổi public loading contract.

### 8.5. Lấy JDBC connection

Khi cần chạy JDBC work trong context Hibernate, xem public `Session.doWork(...)`/`doReturningWork(...)`:

~~~java
Session session = entityManager.unwrap(Session.class);

session.doWork(connection -> {
    try (PreparedStatement ps =
            connection.prepareStatement("select 1");
         ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // ...
        }
    }
});
~~~

Không lấy `JdbcCoordinator`, connection provider implementation hoặc internal logical connection chỉ để thực thi SQL. `doWork` giúp Hibernate điều phối work trên connection thích hợp theo Session contract.

## 9. Dấu hiệu code đang phụ thuộc internal API

### 9.1. Import implementation class

~~~java
import org.hibernate.internal.SessionImpl;
import org.hibernate.engine.internal.StatefulPersistenceContext;
~~~

Đây là dấu hiệu cần xem lại. Hãy tìm public Session/JPA operation hoặc documented SPI.

### 9.2. Cast từ interface sang implementation

~~~java
Session session = entityManager.unwrap(Session.class);
SessionImpl impl = (SessionImpl) session;
~~~

Code đã gắn chặt với class implementation cụ thể. Khi Hibernate đổi implementation, proxy/wrapper hoặc Session implementation, cast có thể fail.

### 9.3. Reflection vào field/method private

~~~java
Field field = someHibernateObject.getClass()
    .getDeclaredField("persistenceContext");

field.setAccessible(true);
Object value = field.get(someHibernateObject);
~~~

Rủi ro:
- Field có thể rename/remove.
- Class hierarchy có thể thay đổi.
- Java module/access rules có thể chặn reflection.
- Runtime hardening/native image có thể hạn chế reflective access.
- Reflection phá abstraction và khó debug.
- Một field có thể không giữ cùng semantics giữa versions.

Reflection không phải extension point chỉ vì có thể truy cập thành công.

### 9.4. Subclass internal implementation

~~~java
class CustomSession extends SessionImpl {
    // Override internal methods...
}
~~~

Đây là coupling rất cao:
- Constructor có thể đổi.
- Invariants nội bộ có thể thay.
- Override hook có thể không còn được gọi.
- Internal call graph thay đổi.
- Binary linkage có thể vẫn thành công nhưng behavior sai.

Tìm interceptor/listener/SPI phù hợp thay vì subclass implementation.

### 9.5. Dựa vào SQL nội bộ hoặc alias generated

Ví dụ test/application code dựa vào:
- Alias kiểu `purchaseor0_` Hibernate tự tạo.
- SQL string exact có whitespace/column order nội bộ.
- Tên bảng/column trong temp table do provider sinh.
- Internal identifier generator state.
- Entity persister metadata không được công bố.

Những chi tiết đó có thể đổi giữa patch/minor/major releases hoặc theo dialect. Nếu mục tiêu là kiểm thử behavior, assert kết quả/database state; chỉ assert SQL shape khi đó là chủ đích cụ thể và được cô lập theo version.

## 10. Compatibility có nhiều chiều

Một ứng dụng có thể compile thành công sau khi nâng Hibernate nhưng vẫn không tương thích về behavior.

### 10.1. Source compatibility

Source compatibility là code có còn compile với API version mới không.

Ví dụ:
- Method bị rename.
- Parameter type thay đổi.
- Package/class chuyển vị trí.
- Generic signature đổi.
- Deprecated API bị xóa.

Compiler bắt được nhiều lỗi này nếu dependency version được cập nhật thật sự.

### 10.2. Binary compatibility

Binary compatibility liên quan bytecode đã compile có liên kết được với library mới không.

Lỗi thường gặp:
- `NoSuchMethodError`
- `NoSuchFieldError`
- `AbstractMethodError`
- `NoClassDefFoundError`
- `IncompatibleClassChangeError`

Ví dụ app compile với Hibernate version A nhưng runtime classpath nạp version B do dependency conflict. Source code có thể compile trên build machine nhưng production nạp artifact khác.

### 10.3. Behavioral compatibility

Code vẫn compile và load được nhưng behavior đổi:
- Auto-flush timing.
- Lazy/eager fetching behavior.
- SQL generated hoặc bind parameter types.
- Query result handling.
- Exception type/timing.
- Identifier generation.
- Locking/transaction behavior.
- Dirty checking và type equality semantics.

Đây là lý do integration tests cần chạy sau nâng cấp.

### 10.4. Configuration compatibility

Properties có thể:
- Đổi tên.
- Được deprecate.
- Đổi default.
- Chuyển namespace.
- Không còn được đọc trong version mới.
- Được Boot override bằng auto-configuration.

Không chỉ kiểm tra Java imports; hãy kiểm tra `hibernate.*`, Spring Boot properties, dialect config, naming strategies, cache và connection settings.

### 10.5. Schema/database compatibility

Một Hibernate upgrade có thể ảnh hưởng:
- Dialect selection.
- DDL generation.
- Type mappings.
- Sequence/identity handling.
- Index/constraint DDL.
- SQL function rendering.
- Pagination/locking syntax.
- Migration behavior.

Schema production nên được quản lý bằng migrations. Không để Hibernate tự thay schema production khi chỉ muốn nâng ORM library.

### 10.6. Integration compatibility

Các thành phần khác có thể phụ thuộc Hibernate:
- Spring ORM/Boot.
- Hibernate Envers.
- Hibernate Search.
- Connection pool.
- Cache provider.
- Bytecode enhancement plugin.
- Custom Integrator/Interceptor.
- Observability/tracing agent.

Cần nâng version matrix phù hợp; không chỉ đổi `hibernate-core` một mình rồi hy vọng mọi extension tương thích.

### 10.7. Bảng tổng hợp

| Compatibility | Câu hỏi | Cách phát hiện |
|---|---|---|
| Source | Code còn compile? | Compile/build |
| Binary | Runtime bytecode có link đúng? | Runtime smoke test, dependency tree |
| Behavioral | SQL/transaction/fetch có đổi? | Integration/regression tests |
| Configuration | Properties/defaults còn đúng? | Config audit, startup logs |
| Schema | DDL/type/index còn đúng? | Migrations và DB tests |
| Integration | Spring/extensions/cache có tương thích? | Version matrix, context tests |
| Performance | Query count/plan/latency có đổi? | Baseline benchmark/APM |
+
## 11. Vì sao nâng cấp major version dễ lộ internal dependency?

Một major release thường là thời điểm thư viện có thể thay đổi public APIs theo migration policy, và refactor internal implementation mạnh hơn.

Hibernate ORM đã trải qua những thay đổi lớn giữa các major generations, ví dụ:
- Chuyển hệ sinh thái Jakarta Persistence từ `javax.persistence` sang `jakarta.persistence` ở thế hệ Hibernate 6.
- Thay đổi type system và SQL generation architecture.
- Thay đổi API/mapping/deprecation qua các version.
- Điều chỉnh Dialect và integration contracts.

Nếu application phụ thuộc `Session`/JPA public contracts, migration có thể cần sửa có giới hạn. Nếu application đọc trực tiếp `EntityPersister`, `PersistenceContext` internals hoặc `SessionImpl` fields, một refactor nội bộ có thể làm hàng loạt packages fail.

**Internal code không có nghĩa chắc chắn sẽ đổi mỗi release; nó có nghĩa ứng dụng không nên dựa vào cam kết ổn định trừ khi tài liệu nói rõ.**

## 12. Quy trình nâng cấp Hibernate có kiểm soát

### 12.1. Bước 1 — Ghi nhận baseline

Trước khi đổi version:
- Hibernate ORM version hiện tại.
- Jakarta Persistence version.
- Spring Boot/Spring Framework version.
- Database engine/version.
- JDBC driver.
- Cache/Envers/Search/extensions.
- Bytecode enhancement plugin.
- Custom types, listeners, interceptors, integrators.
- Migrations đang ở version nào.
- Query/performance baseline.
- Integration tests đang pass.

Lưu dependency tree/lockfile và test report để so sánh.

### 12.2. Bước 2 — Đọc migration guide theo từng major

Đọc:
- Release notes cho từng major/minor cần đi qua.
- Migration guide.
- Deprecation/removal notes.
- Javadocs của target version.
- Compatibility notes của Spring Boot/platform BOM.
- Notes của database dialect và extension modules.

Không nhảy qua các breaking changes trung gian chỉ vì target version mới nhất compile được.

### 12.3. Bước 3 — Tìm toàn bộ internal imports

Dùng search trong repository để tìm:

~~~text
org.hibernate.internal
org.hibernate.engine.internal
org.hibernate.boot.internal
SessionImpl
SessionFactoryImpl
PersistenceContext
EntityPersister
JdbcCoordinator
~~~

Danh sách này là điểm bắt đầu để review, không phải mọi occurrence đều phải xóa: một custom extension có thể được tài liệu yêu cầu dùng một SPI type. Phân loại từng dependency:
- Public API.
- Documented SPI.
- Incubating/deprecated.
- Internal/reflective.
- Chỉ xuất hiện trong test code.

### 12.4. Bước 4 — Tìm reflection và assumptions

Search:
- `getDeclaredField`
- `getDeclaredMethod`
- `setAccessible`
- Cast `unwrap(...).getClass()`
- Class-name string trong configuration.
- `META-INF/services` registrations.
- Custom dialect/interceptor/listener.
- SQL assertions hard-code aliases.

Kiểm tra cả XML/configuration/ServiceLoader files, không chỉ Java imports.

### 12.5. Bước 5 — Tìm replacement contract

Với mỗi dependency không ổn định:
1. Xác định chính xác use case.
2. Tìm API cấp cao hơn.
3. Đọc Hibernate extension guide.
4. Kiểm tra SPI tương đương.
5. Xác định behavior khác biệt.
6. Viết test trước khi thay.
7. Giữ implementation adapter để giới hạn coupling.

Không thay `SessionImpl` bằng một SPI khác chỉ vì compile; thay bằng API đúng với nhu cầu thực tế.

### 12.6. Bước 6 — Nâng dependency một cách nhất quán

Nếu dùng Spring Boot, để Boot BOM quản lý Hibernate version trừ khi có lý do tương thích được xác nhận để override.

Không trộn:
- `hibernate-core` version A.
- `hibernate-envers` version B.
- `hibernate-spatial` version C.
- Một integration module build cho major khác.

Kiểm tra dependency insight/tree để chắc runtime không nạp nhiều version hoặc version khác compile classpath.

### 12.7. Bước 7 — Chạy build và integration tests

Thứ tự hợp lý:
1. Compile main/test sources.
2. Chạy unit tests.
3. Khởi động Spring ApplicationContext.
4. Chạy JPA repository tests.
5. Chạy database-specific Testcontainers tests.
6. Chạy migration tests trên database trống.
7. Chạy transaction/locking/concurrency tests.
8. So sánh SQL/query counts và performance baseline.
9. Kiểm tra warning/deprecation logs.

Nếu test chỉ chạy H2 trong khi production PostgreSQL, chưa đủ chứng minh dialect-specific behavior.

### 12.8. Bước 8 — Rollout và quan sát

Trong môi trường staging/canary:
- Quan sát startup warnings và SQL errors.
- Theo dõi connection pool, lock waits và deadlocks.
- So sánh query fingerprints và p95/p99.
- Theo dõi optimistic lock failures.
- Kiểm tra cache behavior.
- Xác nhận migrations/schema đúng.
- Có rollback plan tương thích schema và application version.

## 13. Tổ chức code để giới hạn Hibernate coupling

### 13.1. Đặt provider-specific code sau adapter

Thay vì để toàn bộ domain/application phụ thuộc Hibernate:

~~~text
application/
  service/
  domain/

persistence/
  jpa/
    UserRepositoryAdapter.java
    HibernateSessionAdapter.java
    HibernateSqlInspector.java
~~~

Ví dụ:

~~~java
public interface PersistenceOperations {
    void flush();
    boolean isInitialized(Object association);
}
~~~

Implementation Hibernate:

~~~java
@Component
public class HibernatePersistenceOperations
        implements PersistenceOperations {

    private final EntityManager entityManager;

    public HibernatePersistenceOperations(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Override
    public void flush() {
        entityManager.flush();
    }

    @Override
    public boolean isInitialized(Object association) {
        return Hibernate.isInitialized(association);
    }
}
~~~

Đây là ví dụ cho thấy coupling được gom trong persistence adapter. Không cần tạo abstraction cho mọi Hibernate method; tạo khi nó bảo vệ boundary có giá trị hoặc khi provider portability thực sự là requirement.

### 13.2. Đừng bọc toàn bộ JPA/Hibernate thành framework riêng

Một anti-pattern khác là tạo hàng chục wrapper cho mỗi `EntityManager` method. Điều này:
- Che mất semantics chuẩn.
- Tạo API nội bộ khó hiểu.
- Tăng boilerplate.
- Không giảm coupling thực sự nếu wrapper expose nguyên Hibernate types.

Giữ standard JPA API trực tiếp ở tầng persistence khi đủ; chỉ cô lập extension/provider-specific logic quan trọng.

### 13.3. Không expose Hibernate SPI trong domain API

Tránh method signature public của application:

~~~java
public void process(SessionFactoryImplementor factory) {
    // ...
}
~~~

Một domain/service API không nên buộc consumer biết internal SPI type. Đặt integration trong infrastructure module hoặc dùng application-owned interface với contract nhỏ.

### 13.4. Version-specific adapter

Nếu một SPI buộc phải dùng và có thể đổi theo Hibernate major, cô lập nó:

~~~text
hibernate-integration/
  v6/
    Hibernate6Integrator.java
    Hibernate6EventRegistration.java
  application/
    DomainEventPublisher.java
~~~

Không nhất thiết tạo module `v6` cho mọi ứng dụng; ý tưởng là thay đổi version-specific nằm ở một nơi thay vì lan khắp codebase.

## 14. Dependency management và classpath hygiene

### 14.1. Để platform BOM quản lý versions

Spring Boot thường cung cấp dependency management cho Hibernate. Nếu app dùng Boot, ưu tiên version được Boot release train hỗ trợ.

Nếu cần override:
- Xác nhận Boot version support target Hibernate.
- Xác nhận JPA API version.
- Đồng bộ các Hibernate modules.
- Kiểm tra transitive dependencies.
- Chạy đầy đủ integration suite.
- Ghi lý do và ngày review.

### 14.2. Kiểm tra dependency tree

Gradle:

~~~bash
./gradlew dependencyInsight --dependency hibernate-core --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.hibernate
~~~

Tìm:
- Hai version cùng group/artifact.
- Dependency bị force/strictly pin.
- Runtime version khác compile version.
- Extension module không tương thích.
- Hibernate 5 artifact còn sót trong ứng dụng Hibernate 6/7.

### 14.3. Không compile against implementation artifact một cách vô tình

Nếu application import internal class, compile dependency `hibernate-core` làm class accessible; compiler không cảnh báo rằng đây là unsupported contract.

Một cách phòng ngừa là:
- Code review rule cho `org.hibernate.*.internal`.
- Static analysis/import allowlist.
- ArchUnit rule ngăn application/domain modules phụ thuộc internal packages.
- CI scan dependencies/source.
- ADR ghi nhận SPI được phép.

### 14.4. Ví dụ ArchUnit rule

~~~java
@AnalyzeClasses(packages = "com.example")
class HibernateBoundaryTest {

    @ArchTest
    static final ArchRule noHibernateInternals =
        noClasses()
            .should().dependOnClassesThat()
            .resideInAnyPackage(
                "org.hibernate..internal.."
            );
}
~~~

Rule này minh họa ngăn dependency vào packages có segment `internal`. Có thể cần điều chỉnh package pattern/allowlist theo ArchUnit version và dự án. Nếu integration module được phép dùng SPI, tạo rule riêng thay vì cấm toàn bộ `org.hibernate.*`.

## 15. Khi nào chấp nhận phụ thuộc SPI?

Không phải mọi SPI dependency đều sai. Một framework integration có thể cần đăng ký event listener hoặc custom service mà public API cấp cao không đáp ứng.

Hãy dùng SPI khi:
- Có use case cụ thể, không chỉ vì SPI “cho phép làm nhiều hơn”.
- Hibernate documentation hoặc extension guide chỉ rõ contract.
- Không có public API đơn giản hơn.
- Team hiểu lifecycle, thread-safety, ordering và transaction semantics.
- Có tests chạy trên Hibernate versions được hỗ trợ.
- Có owner theo dõi migration guides.
- Có adapter/isolated module để thay đổi khi upgrade.
- Có kế hoạch khi SPI bị deprecate hoặc thay đổi.

### 15.1. Đánh giá chi phí trước khi chọn SPI

| Câu hỏi | Nếu câu trả lời là “không” |
|---|---|
| Có tài liệu chính thức cho extension point này không? | Tìm cách khác hoặc xác nhận với maintainers |
| Có API cấp cao hơn đáp ứng không? | Tránh SPI nếu không cần |
| Có test trên DB/Hibernate target không? | Chưa đủ bằng chứng để triển khai |
| Có owner nâng cấp không? | Rủi ro dependency sẽ bị bỏ quên |
| Có thể cô lập implementation không? | Refactor có thể lan rộng |
| Có biết thread/lifecycle semantics không? | Chưa nên đăng ký extension toàn cục |

### 15.2. Nếu bắt buộc dùng internal API?

Đây là trường hợp ngoại lệ, ví dụ integration chưa có hook chính thức. Trước khi quyết định:
- Kiểm tra issue/discussion chính thức hoặc hỏi maintainers.
- Ghi rõ internal type/version trong ADR.
- Pin Hibernate version cụ thể.
- Thêm integration test bảo vệ behavior.
- Dùng reflection có kiểm soát chỉ khi không còn lựa chọn và hiểu Java module/security implications.
- Đặt adapter trong module riêng.
- Xác định version nâng cấp sẽ phải review lại.
- Không coi việc build pass hôm nay là cam kết hỗ trợ từ Hibernate.

Đây là một **technical debt được chấp nhận có chủ đích**, cần owner và thời hạn review.
+
## 16. Trường hợp Hibernate 5 → 6 và javax → jakarta

Một ví dụ lớn về compatibility là chuyển từ thế hệ Hibernate dùng Java EE/JPA namespace cũ sang Jakarta namespace.

### 16.1. Import packages thay đổi

Trước:

~~~java
import javax.persistence.Entity;
import javax.persistence.EntityManager;
import javax.persistence.ManyToOne;
~~~

Sau:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.EntityManager;
import jakarta.persistence.ManyToOne;
~~~

Đây không chỉ là rename import; dependencies và ecosystem integrations phải cùng chuyển sang Jakarta-compatible versions.

### 16.2. Không thể giữ lẫn hai Persistence APIs

Nếu một entity dùng `javax.persistence.Entity` trong khi Hibernate version mục tiêu nhận `jakarta.persistence.Entity`, annotation cũ không phải annotation tương đương mà provider đang tìm.

Kiểm tra:
- Imports trong main/test source.
- Dependencies `javax.persistence` còn sót.
- XML mapping namespaces.
- Custom annotations/listeners.
- Test libraries và code generation.
- Spring Boot version.

### 16.3. Hibernate 6 thay đổi nhiều hơn namespace

Các major changes còn có:
- Type system và JDBC type handling.
- Query/SQL generation.
- Dialect behavior.
- Custom type extensions.
- Deprecated API removals.
- Native SQL and result mapping behavior.

Đừng coi chuyển namespace bằng search/replace là hoàn thành migration. Chạy integration tests trên DB thật, đặc biệt với native queries, custom types, identifier generation và schema.

### 16.4. Custom type/SPI cần review riêng

Code dùng `UserType`, `BasicType`, `TypeContributor`, `Dialect` hoặc internal type registry có thể cần chuyển đổi theo version. Không copy implementation cũ rồi chỉ đổi import. Đọc migration guide về type system và examples tương ứng target version.

## 17. API stability và SemVer: đừng suy luận quá mức

Một thư viện có thể dùng semantic versioning, versioning policy riêng hoặc nhiều module có release cadence khác nhau. Đừng áp dụng quy tắc SemVer chung mà không đọc chính sách Hibernate.

Những điều nên kiểm tra:
- Version scheme của Hibernate ORM.
- Public API compatibility policy.
- SPI compatibility notes.
- Major/minor release notes.
- Jakarta Persistence version được hỗ trợ.
- Module compatibility matrix.
- JDK baseline.
- Deprecated/removed APIs.

**Cùng major version không bảo đảm mọi internal implementation giữ nguyên.** Ngược lại, một public API có thể được hỗ trợ qua nhiều major versions theo policy nhưng vẫn có deprecations cần xử lý.

Không hứa hẹn “public API không bao giờ đổi”; hãy dựa trên compatibility policy và release notes cụ thể.

## 18. Testing chiến lược để bắt compatibility problems

### 18.1. Compile tests

Bắt:
- Imports không còn.
- Method signatures đổi.
- Deprecated API warnings nếu bật compiler warnings.
- Type incompatibility.

Không bắt behavioral differences.

### 18.2. Context/bootstrap test

Khởi động Spring ApplicationContext/SessionFactory để bắt:
- SPI registration thất bại.
- Service loading không tìm được class.
- Dialect/bootstrap configuration sai.
- Type contributor/interceptor initialization fail.
- Dependency linkage errors.

### 18.3. Database integration tests

Dùng Testcontainers với database production engine để kiểm tra:
- Migrations.
- SQL generation.
- Native query.
- Constraints/indexes.
- Flush/commit.
- Locking/isolation.
- Lazy/eager fetching.
- Custom types/functions.

### 18.4. Regression tests cho extension point

Nếu có listener/interceptor/Integrator:
- Assert nó được đăng ký đúng một lần.
- Assert event được gọi đúng trường hợp.
- Assert bulk DML/native SQL behavior theo design.
- Assert transaction rollback không phát side effects sai.
- Assert listener thread safety/tenant isolation.
- Assert bootstrap và shutdown cleanup.

### 18.5. Performance baseline

Một API có thể vẫn hoạt động nhưng query count hoặc execution plan thay đổi. Theo dõi:
- SQL fingerprints.
- SELECT/UPDATE counts.
- JDBC batches.
- Entity/collection fetches.
- p95/p99 latency.
- DB CPU/locks.
- Heap và persistence context size.

Không chỉ so sánh thời gian của một test chạy trên laptop; dùng dataset và environment đại diện.
+
## 19. Troubleshooting khi nâng Hibernate

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| `cannot find symbol` | Public API đã đổi/xóa hoặc dependency sai | Javadocs, migration guide, compile classpath |
| `NoSuchMethodError` | Runtime artifact version khác compile version | Dependency tree/runtime classpath |
| `NoClassDefFoundError` | Module thiếu hoặc class chuyển package | Align Hibernate modules và integrations |
| `ClassCastException: SessionImpl` | Code cast vào implementation cụ thể | Dùng `Session` contract hoặc adapter |
| `IllegalAccessException` khi reflection | Java module/security hoặc field access đổi | Bỏ internal reflection, dùng extension point |
| Integrator không được load | ServiceLoader/config/registration thay đổi | Kiểm tra SPI docs và `META-INF/services` |
| Listener không chạy | Event type/order/registration thay đổi hoặc code dùng bulk DML | Kiểm tra event lifecycle và query path |
| Custom Type không compile | Type system/API thay đổi | Migration guide và target-version extension examples |
| SQL khác trước | Dialect/query translation/version behavior | Log SQL, DB integration test, release notes |
| Native query mapping lỗi | Result mapping/type inference thay đổi | Explicit mapping, test trên DB thật |
| Lazy behavior khác | Fetch plan/proxy/enhancement change | Integration test và SQL traces |
| Flush timing khác | Flush mode/query space/provider behavior | Test transaction boundaries và SQL order |
| Schema validation fail | Mapping/DDL type khác | Migration/schema diff; không auto-update production |
| Spring context không khởi động | Boot/Hibernate version matrix lệch | Dùng Boot BOM compatible |
| Envers/Search không tương thích | Extension module version khác | Align module release train |
| Deprecation warning mới | API sắp bị thay thế | Tìm replacement, lên migration plan |
| `@Incubating` API biến mất | Feature chưa có stability guarantee | Thay bằng stable API hoặc cập nhật adapter |
| Query count tăng | Fetch strategy/SQL generation thay đổi | JDBC trace, fetch plan, regression budget |
| Performance giảm dù test pass | Plan/row volume/lock behavior đổi | EXPLAIN, DB telemetry, benchmark |
| Internal package import còn sót | Application coupling với implementation | Source scan/ArchUnit rule |
| Test pass với H2, fail PostgreSQL | Dialect/constraint semantics khác | Testcontainers với production DB |

## 20. Checklist đánh giá một API trước khi phụ thuộc

Trước khi import hoặc implement một Hibernate type, hỏi:

1. Nó thuộc Jakarta Persistence hay Hibernate-specific?
2. Javadoc có gọi nó là public API, extension point hay internal?
3. Package có `.spi` hoặc `.internal` không?
4. Có `@Incubating`, `@Internal`, `@Deprecated` hoặc migration note không?
5. Có public API cấp cao hơn đáp ứng use case không?
6. Có được Hibernate documentation dùng trong extension guide không?
7. Compatibility policy của version hiện tại nói gì?
8. API có expose vào domain/application interfaces không?
9. Có thể cô lập trong adapter/module không?
10. Có integration tests chạy với Hibernate/DB version mục tiêu không?
11. Có kiểm tra thread safety, lifecycle và transaction semantics không?
12. Ai chịu trách nhiệm theo dõi release notes và nâng cấp?
+
## 21. Bài tập thực hành

### Bài 1 — public có đồng nghĩa supported API?

Một class `public` trong `org.hibernate.internal` có thể được import.

**Hỏi:** Có nên dùng trong repository không?

**Đáp án:** Không nên mặc định. `public` chỉ là Java accessibility; package và compatibility contract cho thấy nó là implementation detail.

### Bài 2 — API hay SPI?

`Session` là interface mà application gọi để thao tác Hibernate Session.

**Đáp án:** Hibernate public API.

### Bài 3 — Jakarta hay Hibernate-specific?

`EntityManager` thuộc package `jakarta.persistence`.

**Đáp án:** Jakarta Persistence API, có portability contract giữa các providers hỗ trợ spec.

### Bài 4 — Integrator

Một extension implement `org.hibernate.integrator.spi.Integrator`.

**Đáp án:** Đây là SPI dành cho integration/bootstrap, cần theo dõi version contract và migration guide.

### Bài 5 — @Incubating

Một method có annotation `@Incubating`.

**Hỏi:** Có thể coi nó stable vì đang public không?

**Đáp án:** Không. Annotation báo API đang phát triển và có thể đổi; kiểm tra Javadoc/release notes.

### Bài 6 — @Internal

Một helper được đánh dấu `@Internal`.

**Hỏi:** Có nên dùng nếu nó giải quyết bài toán rất nhanh?

**Đáp án:** Chỉ xem xét như technical debt ngoại lệ sau khi tìm public API/SPI và chấp nhận chi phí upgrade; không coi nó là supported contract.

### Bài 7 — SessionImpl

Code cast `Session` sang `SessionImpl` chỉ để gọi `flush()`.

**Đáp án:** Dùng `Session.flush()` hoặc `EntityManager.flush()`; không cần implementation cast.

### Bài 8 — Kiểm tra managed entity

Code truy cập internal `EntityEntry` để biết entity còn managed không.

**Đáp án:** Dùng `EntityManager.contains(entity)` cho câu hỏi này.

### Bài 9 — Lazy initialization

Code đọc private proxy initializer field bằng reflection.

**Đáp án:** Dùng `Hibernate.isInitialized()` hoặc JPA `PersistenceUtil.isLoaded()` theo semantics cần thiết.

### Bài 10 — SQL inspection

Ứng dụng cần inspect SQL string trước khi Hibernate gửi JDBC.

**Đáp án:** Xem `StatementInspector`, không truy cập internal JDBC coordinator.

### Bài 11 — Lifecycle callback

Ứng dụng chỉ cần gán `createdAt` trước insert.

**Đáp án:** JPA `@PrePersist` hoặc application/domain factory thường đủ; không cần Hibernate event SPI.

### Bài 12 — After commit email

Ứng dụng muốn gửi email sau khi transaction tạo order commit.

**Đáp án:** Dùng transaction-aware event/outbox pattern; không gửi email trong `@PrePersist` hay listener trước commit.

### Bài 13 — Custom SQL function

Ứng dụng muốn đăng ký function cho HQL.

**Đáp án:** Kiểm tra Dialect/API có sẵn và `FunctionContributor` trong Hibernate version hỗ trợ; tránh sửa internal SQL AST registry.

### Bài 14 — Custom value type

Một value object chuyển đổi thành một VARCHAR.

**Đáp án:** Xem JPA `AttributeConverter` trước custom Hibernate `UserType`.

### Bài 15 — NoSuchMethodError

Build compile thành công nhưng production lỗi `NoSuchMethodError`.

**Đáp án:** Kiểm tra runtime dependency tree; runtime có thể nạp Hibernate artifact version khác compile classpath.

### Bài 16 — Deprecated method

Một method deprecated nhưng replacement có behavior khác.

**Đáp án:** Đọc migration notes, viết regression test và chuyển theo semantics; không thay tên máy móc.

### Bài 17 — javax và jakarta

Entity dùng `javax.persistence.Entity` nhưng Hibernate target chờ Jakarta Persistence.

**Đáp án:** Đây là namespace/API generation mismatch; cập nhật toàn bộ dependencies/imports/integrations tương thích.

### Bài 18 — Hibernate 6 upgrade

Một custom type dùng internal type registry từ Hibernate 5.

**Đáp án:** Đọc migration guide type system, tìm public type extension contract của target version và test JDBC binding/extraction.

### Bài 19 — Internal dependency scan

Repository có nhiều imports `org.hibernate.engine.internal`.

**Đáp án:** Phân loại từng dependency, tìm API/SPI thay thế và có thể thêm ArchUnit/source rule để ngăn phát sinh mới.

### Bài 20 — H2 pass, PostgreSQL fail

Một query dùng `ON CONFLICT ... RETURNING`.

**Đáp án:** Đây là PostgreSQL-specific SQL; dùng PostgreSQL Testcontainer để kiểm tra syntax/semantics.

### Bài 21 — SPI có phải luôn cấm?

Một framework integration cần `Integrator` để đăng ký listener.

**Đáp án:** Không. Dùng documented SPI khi cần, nhưng cô lập, theo dõi compatibility và test bootstrap/event behavior.

### Bài 22 — Reflection field đổi tên

Sau upgrade, `getDeclaredField("persistenceContext")` thất bại.

**Đáp án:** Code phụ thuộc internal structure; thay bằng public API/SPI, không tiếp tục dò field mới.

### Bài 23 — API có mặt trong Javadoc

Một internal class có trang Javadoc public.

**Đáp án:** Javadoc visibility không tự tạo compatibility guarantee; đọc package/annotation/contract.

### Bài 24 — Dependency BOM

Spring Boot quản lý Hibernate version nhưng build file override riêng `hibernate-core`.

**Đáp án:** Có nguy cơ lệch version với Envers/extension/Spring integration; kiểm tra Boot compatibility matrix và align module versions.

### Bài 25 — Public API vẫn đổi behavior?

Sau upgrade, code compile nhưng auto-flush xảy ra ở query boundary khác.

**Đáp án:** Đây là behavioral compatibility issue; kiểm tra release notes, flush mode/query spaces và integration tests.

### Bài 26 — Performance regression

Query count tăng sau upgrade dù không có compile errors.

**Đáp án:** So sánh SQL fingerprints, fetch plan, execution plan, cache state và JDBC timings; compile pass không chứng minh performance giữ nguyên.

### Bài 27 — Internal API ngoại lệ

Không có extension point public/SPI đáp ứng requirement, team phải dùng internal hook.

**Đáp án:** Ghi ADR/technical debt, pin version, cô lập adapter, integration test và chỉ định owner theo dõi upgrade.

### Bài 28 — Khi nào chọn JPA thay Hibernate API?

Ứng dụng cần có khả năng thay provider trong tương lai và không cần Hibernate-specific features ở service layer.

**Đáp án:** Ưu tiên Jakarta Persistence API ở boundary; giữ provider-specific code trong infrastructure adapter.

## 22. Tổng kết

### 22.1. Bảng nhớ nhanh

| Loại | Ví dụ | Quyết định |
|---|---|---|
| Jakarta Persistence API | `EntityManager`, `Query`, `@Version` | Ưu tiên cho portability |
| Hibernate public API | `Session`, `SessionFactory`, `Hibernate` | Dùng khi cần Hibernate-specific features |
| Hibernate annotations/API | `@SoftDelete` và các extensions được công bố | Kiểm tra stability/version notes từng type |
| Hibernate SPI | `Integrator`, documented listener/type extension contracts | Dùng cho integration có chủ đích, cô lập và test |
| Internal implementation | `SessionImpl`, `org.hibernate.*.internal.*` | Tránh dependency trực tiếp |
| Incubating API | Type/method có `@Incubating` | Chấp nhận rủi ro thay đổi có chủ đích |
| Deprecated API | `@Deprecated` | Có migration plan, tìm replacement |

### 22.2. Ba nguyên tắc

**Một:** Java accessibility không phải compatibility contract. Class `public` vẫn có thể là internal implementation.

**Hai:** Không phải mọi Hibernate-specific API đều xấu. `Session`, `StatementInspector` hay documented SPI có thể là lựa chọn đúng; điều quan trọng là biết mình đang phụ thuộc vào contract nào.

**Ba:** Upgrade không chỉ là làm code compile. Cần kiểm tra binary classpath, behavior, configuration, schema, integrations và performance trên stack thực.

### 22.3. Quy trình ghi nhớ

~~~text
Cần mở rộng Hibernate?
          |
          v
Có Jakarta Persistence API phù hợp?
      /               \
    Có                 Không
    |                   |
    v                   v
Dùng JPA         Có Hibernate public API?
                       /       \
                     Có        Không
                     |           |
                     v           v
               Dùng API      Có documented SPI?
                               /       \
                             Có        Không
                             |           |
                             v           v
                       Cô lập SPI   Đánh giá thiết kế/
                       + test       internal exception
~~~

### 22.4. Tài liệu chính thức

- [Hibernate ORM Documentation](https://docs.hibernate.org/orm/) — User Guide và API/Javadocs theo version.
- [Hibernate ORM 6.6 Javadocs](https://docs.hibernate.org/orm/6.6/javadocs/) — phân loại public types, annotations và SPI contracts.
- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html) — API và các extension mechanisms.
- [Hibernate ORM Migration Guides](https://hibernate.org/orm/releases/) — release notes, migration changes theo release.
- [Hibernate Integrator Javadoc](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/integrator/spi/Integrator.html) — bootstrap integration SPI.
- [Hibernate StatementInspector Javadoc](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/resource/jdbc/spi/StatementInspector.html) — SQL inspection contract.
- [Hibernate Interceptor Javadoc](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/Interceptor.html) — entity/session interception.
- [Hibernate Incubating annotation](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/Incubating.html) — API stability signal.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — portable persistence contract.
- [Spring Boot Dependency Versions](https://docs.spring.io/spring-boot/reference/dependency-versions.html) — dependency management/version alignment.
- [Spring Boot Data JPA](https://docs.spring.io/spring-boot/reference/data/sql.html#data.sql.jpa-and-spring-data) — Hibernate/JPA integration.
- [ArchUnit User Guide](https://www.archunit.org/userguide/html/000_Index.html) — enforce architecture boundaries.

> Package names và API examples trong bài là định hướng cho Hibernate ORM 6.x, đặc biệt các Javadocs 6.6 được liên kết. Kiểm tra đúng Javadoc/migration guide của version ứng dụng sử dụng; các extension signatures và stability annotations có thể khác theo release. Không suy luận rằng một type ổn định chỉ từ tên package hoặc modifier `public`.

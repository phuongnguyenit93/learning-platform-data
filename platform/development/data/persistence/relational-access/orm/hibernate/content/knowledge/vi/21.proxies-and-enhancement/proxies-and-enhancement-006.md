# Unproxy và cách xác định kiểu khi cần làm việc với thực thể thực

Hibernate có thể trả về một **proxy** thay cho entity đã được tải đầy đủ. Proxy là đối tượng đại diện cho một entity theo định danh, cho phép trì hoãn việc đọc trạng thái từ database cho tới khi ứng dụng thật sự cần. Cơ chế này hỗ trợ lazy loading, nhưng cũng tạo ra khác biệt giữa **kiểu Java runtime của object**, **kiểu entity được ánh xạ**, và **lớp thực thể thực đang được đại diện**.

Khi cần gọi API phụ thuộc vào lớp cụ thể, dùng reflection, kiểm tra kiểu trong entity hierarchy, ánh xạ sang DTO hoặc truyền object cho thư viện không hiểu Hibernate proxy, ứng dụng có thể cần xác định kiểu persistent thực hoặc lấy implementation phía sau proxy.

Hibernate cung cấp một số API với mục đích khác nhau:

- `Hibernate.getClass(entity)`: lấy kiểu thực thể phía sau proxy; thao tác này **có thể khởi tạo proxy**.
- `Hibernate.getClassLazy(entity)`: cố gắng lấy kiểu mà **không khởi tạo proxy nếu có thể**; trong trường hợp không xác định được kiểu mà không đọc dữ liệu, proxy vẫn có thể phải initialize.
- `Hibernate.unproxy(entity)`: lấy implementation thực phía sau proxy; nếu cần, Hibernate khởi tạo proxy trước.
- `Hibernate.unproxy(entity, EntityType.class)`: dạng có kiểm tra kiểu để nhận implementation theo kiểu mong muốn.
- `Hibernate.isInitialized()` và `Hibernate.initialize()`: kiểm tra hoặc chủ động khởi tạo proxy/collection.

Các API này là **Hibernate-specific**. Chúng không có nghĩa một object sau unproxy đã tải toàn bộ object graph, và cũng không thay thế việc thiết kế fetch plan, transaction hay DTO.

## 1. Ba khái niệm kiểu cần phân biệt

Xét một entity `Department`:

```java
@Entity
public class Department {
    @Id
    private Long id;

    private String name;
}
```

Khi tải trực tiếp:

```java
Department department = em.find(Department.class, 10L);
```

object trả về thường là một instance của lớp entity hoặc một representation đã được Hibernate enhancement.

Nhưng với:

```java
Department reference = em.getReference(Department.class, 10L);
```

Hibernate có thể trả về một proxy subclass đại diện cho `Department#10`, chưa cần đọc các cột của entity.

Có ba câu hỏi khác nhau:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Runtime Java class** | `object.getClass()` trả về lớp nào? | Có thể là `Department$HibernateProxy$...` |
| **Mapped/persistent class** | Hibernate ánh xạ object tới entity type nào? | `Department.class` |
| **Concrete entity type** | Hàng database thực sự thuộc subtype nào trong inheritance hierarchy? | `CardPayment.class` hoặc `BankTransfer.class` |

Không phải mọi proxy đều làm ba câu trả lời khác nhau. Với entity không có kế thừa, mapped class và concrete entity type thường trùng nhau. Với proxy subclass hoặc quan hệ polymorphic, cần cẩn thận hơn.

### 1.1. Vì sao `getClass()` có thể gây bất ngờ?

```java
Department reference = em.getReference(Department.class, 10L);

System.out.println(reference instanceof Department); // thường true
System.out.println(reference.getClass() == Department.class); // có thể false
```

Hibernate có thể tạo một subclass proxy để chặn các lời gọi method và khởi tạo entity khi cần. Vì vậy runtime class có thể là lớp proxy được sinh ra, dù object đại diện cho một `Department`.

Điều này không có nghĩa proxy là một entity type mới trong mô hình dữ liệu. Nó là representation kỹ thuật của entity được ánh xạ.

## 2. Proxy tồn tại để làm gì?

Một proxy cho phép Hibernate trì hoãn việc tải state:

```java
Department reference = em.getReference(Department.class, 10L);
```

Nếu entity chưa có trong persistence context, Hibernate có thể trả một object proxy chứa thông tin định danh và liên kết tới `Session` cần dùng để load entity khi có yêu cầu.

Mô hình đơn giản:

```text
Ứng dụng
   |
   | em.getReference(Department.class, 10)
   v
Hibernate proxy
   ├─ entity type được ánh xạ
   ├─ identifier = 10
   ├─ trạng thái initialized? có thể là false
   └─ lazy initializer
             |
             | khi cần state thực
             v
       Hibernate Session
             |
             v
       SELECT database
             |
             v
       Entity implementation
```

Lợi ích:

- Gán một quan hệ tới entity khác chỉ bằng identifier mà không cần tải toàn bộ entity.
- Trì hoãn đọc dữ liệu không được dùng.
- Giảm lượng dữ liệu tải trong những use case chỉ cần tham chiếu.
- Hỗ trợ lazy association như `@ManyToOne(fetch = LAZY)`.

Nhưng proxy cũng có giới hạn: nó phụ thuộc persistence context/session để initialize, có thể làm phát SQL bất ngờ và có runtime class khác lớp entity.

### 2.1. `getReference()` không xác nhận hàng tồn tại

```java
Department reference = em.getReference(Department.class, 999L);
```

Provider có thể trả proxy mà chưa thực hiện SELECT. Vì vậy việc gọi thành công `getReference()` **không chứng minh** `Department#999` có trong database.

Khi ứng dụng truy cập một thuộc tính cần khởi tạo proxy, Hibernate mới có thể truy vấn và phát hiện không có hàng, dẫn tới lỗi như `EntityNotFoundException` theo ngữ nghĩa API/provider.

Nếu mục tiêu là kiểm tra entity có tồn tại, dùng `find()` hoặc một truy vấn existence phù hợp. Không dùng `unproxy()` như một phép kiểm tra tồn tại rẻ: unproxy có thể kích hoạt tải dữ liệu.

## 3. Ví dụ entity và quan hệ lazy

```java
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "departments")
public class Department {

    @Id
    private Long id;

    private String name;

    protected Department() {
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

```java
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "employees")
public class Employee {

    @Id
    private Long id;

    private String fullName;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "department_id")
    private Department department;

    protected Employee() {
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public Department getDepartment() {
        return department;
    }
}
```

Khi tải employee:

```java
Employee employee = em.find(Employee.class, 100L);
Department department = employee.getDepartment();
```

Nếu association lazy và chưa có `Department` được managed trong persistence context, `department` có thể là proxy chưa initialized.

Một số quan sát:

```java
System.out.println(department instanceof Department);
System.out.println(department.getClass());
System.out.println(department.getId());
```

Lời gọi getter ID thường có thể được phục vụ từ identifier mà không initialize proxy, tùy mapping/access strategy. Lời gọi `getName()` cần state của entity nên có thể phát SELECT.

**Đừng suy số SQL chỉ từ số method Java được gọi.** Cần xem proxy đã initialized chưa, entity có sẵn trong L1 cache không, và Hibernate version/mapping đang dùng.

## 4. `Hibernate.unproxy()` lấy implementation phía sau proxy

Import:

```java
import org.hibernate.Hibernate;
```

Dùng:

```java
Department reference = em.getReference(Department.class, 10L);

Department actual = Hibernate.unproxy(reference);

System.out.println(actual.getClass());
System.out.println(actual.getName());
```

Với proxy subclass chưa initialized, `Hibernate.unproxy()` yêu cầu Hibernate lấy implementation thật phía sau proxy. Việc đó thường **initialize proxy** và có thể phát SQL.

Nếu `reference` không phải Hibernate proxy, phương thức trả về object hiện có; không có lớp proxy nào cần bóc bỏ.

Có thể dùng overload có kiểu:

```java
Department actual = Hibernate.unproxy(
    reference,
    Department.class
);
```

Overload này hữu ích khi code cần một kiểu kết quả cụ thể và muốn kiểm tra/cast theo kiểu đó. Nếu object không tương thích với kiểu yêu cầu, thao tác có thể thất bại bằng lỗi cast.

### 4.1. Unproxy không phải copy entity

`Hibernate.unproxy()` không tạo một bản sao DTO hoặc clone object graph. Nó trả về implementation đang được proxy đại diện trong persistence context.

Vì vậy:

```java
Department actual = Hibernate.unproxy(reference);

actual.rename("New name");
```

nếu `actual` vẫn managed, thay đổi đó vẫn được Hibernate theo dõi như thay đổi trên entity managed bình thường. Unproxy không detach entity, không commit transaction và không ghi SQL ngay lập tức.

### 4.2. Unproxy không tải toàn bộ quan hệ

Giả sử `Department` có collection lazy:

```java
@OneToMany(mappedBy = "department", fetch = FetchType.LAZY)
private List<Employee> employees;
```

Sau:

```java
Department actual = Hibernate.unproxy(reference);
```

Hibernate đã lấy implementation của `Department`, nhưng `employees` vẫn có thể là collection lazy chưa initialized.

```java
System.out.println(Hibernate.isInitialized(actual.getEmployees()));
```

Có thể vẫn là `false`.

Unproxy giải quyết **proxy của entity được truyền vào**, không tự động fetch mọi association, collection hoặc lazy basic attribute trong graph.

## 5. `Hibernate.getClass()` xác định lớp entity phía sau proxy

Nếu chỉ cần biết class thay vì lấy implementation, có thể dùng:

```java
Class<?> entityClass = Hibernate.getClass(reference);
```

Với một Hibernate proxy, API này trả class của entity được đại diện thay vì runtime subclass proxy.

Ví dụ:

```java
Department reference = em.getReference(Department.class, 10L);

Class<?> runtimeType = reference.getClass();
Class<?> entityType = Hibernate.getClass(reference);

System.out.println(runtimeType.getName());
// Có thể là lớp Hibernate proxy được sinh tự động.

System.out.println(entityType.getName());
// Department.
```

**Lưu ý:** `Hibernate.getClass()` có thể initialize proxy. Nếu mục tiêu chỉ là log/kiểm tra type mà không muốn phát SQL, không nên mặc định gọi API này là miễn phí.

### 5.1. Khi chỉ cần class, không cần unproxy object

Không cần lấy implementation nếu chỉ muốn chọn một nhánh xử lý:

```java
Class<?> type = Hibernate.getClass(entity);

if (type == Department.class) {
    // Xử lý theo entity type.
}
```

Tuy nhiên, vì `getClass()` có thể initialize proxy, hãy cân nhắc `getClassLazy()` hoặc API metadata khác khi việc khởi tạo là điều cần tránh.

Không dùng:

```java
entity.getClass() == Department.class
```

nếu `entity` có thể là proxy subclass.

## 6. `Hibernate.getClassLazy()` khi muốn hạn chế khởi tạo proxy

Các phiên bản Hibernate mới có:

```java
Class<?> entityClass = Hibernate.getClassLazy(entity);
```

Mục đích của API là lấy kiểu entity **mà không initialize proxy nếu Hibernate có thể xác định được kiểu**.

Điều kiện “nếu có thể” rất quan trọng:

- Với proxy có kiểu thực thể đã biết rõ, Hibernate có thể trả mapped type mà không đọc toàn bộ entity.
- Với association polymorphic, proxy có thể chỉ biết declared/root type. Concrete subtype thực sự có thể cần đọc database.
- Nếu không thể xác định kiểu chính xác mà không khởi tạo, Hibernate có thể initialize proxy.

`getClassLazy()` có từ các phiên bản Hibernate mới hơn; hãy kiểm tra Javadoc của **đúng version** đang dùng trước khi gọi. Nếu project chạy Hibernate cũ chưa có method này, không thể thay bằng `Object.getClass()` rồi mong có cùng semantics.

### 6.1. `getClassLazy()` không phải lời hứa “không bao giờ có SQL”

Ví dụ quan hệ polymorphic:

```java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class PaymentInstrument {
    @Id
    private Long id;
}
```

Các subtype:

```java
@Entity
public class CardPayment extends PaymentInstrument {
    private String lastFourDigits;
}

@Entity
public class BankTransfer extends PaymentInstrument {
    private String bankCode;
}
```

Một proxy được tạo từ association khai báo kiểu `PaymentInstrument`. Nếu Hibernate chưa biết hàng cụ thể là `CardPayment` hay `BankTransfer`, muốn trả concrete class chính xác có thể phải truy vấn dữ liệu discriminator/join phù hợp.

Do đó `getClassLazy()` là lựa chọn **cố gắng tránh initialization**, chứ không phải cam kết không truy cập database trong mọi mô hình inheritance.

## 7. So sánh các API xác định kiểu và lấy implementation

| API | Kết quả | Có thể initialize proxy? | Dùng khi |
| --- | --- | --- | --- |
| `object.getClass()` | Runtime Java class | Không tự initialize chỉ để lấy class | Debug runtime object, không phù hợp xác định persistent class |
| `Hibernate.getClass(object)` | Class của entity phía sau proxy | Có thể | Cần entity class chính xác và chấp nhận load nếu cần |
| `Hibernate.getClassLazy(object)` | Cố gắng trả entity class mà không initialize | Có thể nếu không xác định được kiểu | Type check nhạy với SQL, Hibernate version hỗ trợ |
| `Hibernate.unproxy(object)` | Implementation entity phía sau proxy | Có, nếu proxy chưa initialized | Cần thao tác với object thực |
| `Hibernate.unproxy(object, Type.class)` | Implementation với kiểu mong muốn | Có | Cần kết quả typed và kiểm tra kiểu |
| `Hibernate.initialize(object)` | `void`; initialize proxy/collection | Có | Muốn khởi tạo rõ ràng nhưng không cần unwrap |
| `Hibernate.isInitialized(object)` | `boolean` | Không chỉ để kiểm tra | Quan sát trạng thái lazy |
| `PersistenceUnitUtil.getIdentifier(entity)` | Identifier theo JPA | Không nên dựa vào giả định provider cụ thể nếu cần tuyệt đối tránh load | Lấy ID bằng API chuẩn |
| `PersistenceUnitUtil.isLoaded(entity)` | Trạng thái load theo JPA | Không phải yêu cầu unproxy | Kiểm tra trạng thái load portable |

Không có API nào trong bảng vừa trả concrete implementation, vừa đảm bảo không bao giờ phát SQL, vừa tải toàn bộ graph. Hãy chọn theo câu hỏi thực sự của code.

## 8. `unproxy()` khác `initialize()`

Hai API thường bị nhầm:

```java
Hibernate.initialize(reference);
Department actual = Hibernate.unproxy(reference);
```

Khác biệt:

- `initialize()` yêu cầu khởi tạo proxy hoặc collection. Nó trả `void`; biến `reference` vẫn giữ nguyên reference Java đã có.
- `unproxy()` trả implementation entity phía sau proxy. Nếu proxy chưa initialized, thao tác có thể khởi tạo nó.
- Cả hai không tự initialize tất cả association của entity.
- Cả hai cần một context phù hợp nếu dữ liệu lazy chưa được tải.

Ví dụ:

```java
Department reference = em.getReference(Department.class, 10L);

Hibernate.initialize(reference);

System.out.println(Hibernate.isInitialized(reference)); // true
```

Nếu code chỉ cần đọc thuộc tính thông thường, thường không cần gọi initialize/unproxy trước:

```java
String name = reference.getName();
```

Lời gọi method có thể tự kích hoạt lazy initialization. Dùng API tường minh khi muốn **làm rõ ranh giới tải dữ liệu** hoặc cần implementation/type thực sự.

## 9. Unproxy cần persistence context phù hợp

Một proxy chưa initialized thường phụ thuộc `Session` mà nó được tạo ra.

```java
Department reference;

try (EntityManager em = emf.createEntityManager()) {
    reference = em.getReference(Department.class, 10L);
}

// EntityManager đã đóng.
Department actual = Hibernate.unproxy(reference);
```

Nếu proxy chưa initialized và session đã đóng, Hibernate không còn context để tải state. Thao tác có thể ném `LazyInitializationException`.

### 9.1. Unproxy trước khi đóng session

```java
Department actual;

try (EntityManager em = emf.createEntityManager()) {
    Department reference = em.getReference(Department.class, 10L);

    actual = Hibernate.unproxy(reference);

    // Có thể đọc các scalar state đã được initialize.
    System.out.println(actual.getName());
}
```

Sau khi `EntityManager` đóng, `actual` trở thành detached. Những lazy association chưa được khởi tạo vẫn có thể không truy cập được.

### 9.2. Unproxy không mở session mới

Không có nghĩa:

```java
Hibernate.unproxy(detachedProxy);
```

sẽ tự tìm `EntityManagerFactory`, mở connection và load dữ liệu. API dùng cơ chế lazy initializer/session đã gắn với proxy. Nếu context không còn khả dụng, cần tải entity lại qua một context mới bằng ID.

### 9.3. Có nên giữ proxy sau khi session đóng?

Có thể giữ một proxy detached nếu chỉ dùng identifier đã có và không truy cập state cần lazy initialization. Nhưng truyền proxy ra tầng web/serialization thường dễ gây lỗi hoặc vô tình trigger lazy load.

Một quy trình rõ ràng hơn:

1. Mở transaction/context.
2. Tải dữ liệu cần cho use case.
3. Unproxy nếu thư viện thực sự yêu cầu implementation.
4. Ánh xạ sang DTO trong context.
5. Trả DTO ra ngoài.
6. Đóng context.

Không dùng unproxy như giải pháp tổng quát cho `LazyInitializationException`; hãy xác định dữ liệu nào cần tải và ở tầng nào.

## 10. Xác định kiểu khi có entity inheritance

Trong inheritance hierarchy, entity type khai báo và concrete subtype có thể khác nhau.

Ví dụ:

```java
@Entity
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "payment_type")
public abstract class PaymentMethod {

    @Id
    private Long id;

    private BigDecimal amount;
}
```

```java
@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends PaymentMethod {
    private String lastFourDigits;
}
```

```java
@Entity
@DiscriminatorValue("BANK")
public class BankPayment extends PaymentMethod {
    private String bankAccount;
}
```

Một association có thể khai báo:

```java
@ManyToOne(fetch = FetchType.LAZY)
private PaymentMethod paymentMethod;
```

Ứng dụng chỉ biết declared type là `PaymentMethod`, nhưng object thực có thể là `CardPayment` hoặc `BankPayment`.

### 10.1. `instanceof` và proxy subclass

Nếu proxy subclass tương thích với base entity, kiểm tra:

```java
if (paymentMethod instanceof PaymentMethod) {
    // true cho proxy đại diện PaymentMethod.
}
```

thường vẫn hoạt động.

Với subtype:

```java
if (paymentMethod instanceof CardPayment) {
    // Có thể phụ thuộc concrete subtype proxy mà Hibernate tạo.
}
```

Trong polymorphic association, subtype thực có thể chưa được xác định nếu proxy chỉ được tạo theo declared/root type. Khi cần nhánh nghiệp vụ theo concrete subtype, hãy sử dụng API xác định type phù hợp và chấp nhận khả năng load nếu cần.

### 10.2. `getClass()` không phải cách kiểm tra subtype an toàn

```java
if (paymentMethod.getClass() == CardPayment.class) {
    // Có thể false nếu runtime class là proxy subclass.
}
```

Với Hibernate, nếu cần concrete class:

```java
Class<?> concreteType = Hibernate.getClass(paymentMethod);
```

hoặc dùng `getClassLazy()` nếu version hỗ trợ và có thể xác định mà không initialize.

### 10.3. Không thay thế inheritance bằng `instanceof` tùy tiện

Nếu nghiệp vụ chỉ cần hành vi chung, nên khai báo method trên base class/interface:

```java
abstract class PaymentMethod {
    public abstract PaymentSummary toSummary();
}
```

Thay vì liên tục kiểm tra subtype và cast:

```java
if (payment instanceof CardPayment) {
    ...
} else if (payment instanceof BankPayment) {
    ...
}
```

Proxy subclass thường ủy quyền method tới implementation. Thiết kế polymorphism ở domain giúp code ít phụ thuộc runtime proxy details hơn.

## 11. Khi nào cần unproxy thật sự?

Các trường hợp có thể hợp lý:

### 11.1. Thư viện bên ngoài yêu cầu class cụ thể

Một thư viện reflection/serialization cũ kiểm tra chính xác:

```java
object.getClass() == Department.class
```

và không hỗ trợ proxy subclass. Khi đó unproxy trong persistence context có thể giúp truyền implementation.

Tuy nhiên, nếu thư viện chỉ cần dữ liệu, DTO thường là ranh giới ổn định hơn entity/proxy.

### 11.2. Reflection hoặc annotation lookup trên concrete class

Framework nội bộ có thể đọc annotation trên entity class:

```java
Class<?> type = Hibernate.getClass(entity);
SomeAnnotation annotation =
    type.getAnnotation(SomeAnnotation.class);
```

Nếu annotation/metadata lookup không cần object implementation, chỉ cần class. Tránh unproxy toàn bộ object khi `getClassLazy()` hoặc metadata mapping đủ dùng.

### 11.3. Gọi method chỉ có trên subtype

Nếu code nhận base reference nhưng cần API cụ thể:

```java
Object actual = Hibernate.unproxy(paymentMethod);

if (actual instanceof CardPayment cardPayment) {
    cardPayment.authorizeWithToken(token);
}
```

Cần bảo đảm proxy được khởi tạo trong context hợp lệ. Nhưng nếu đây là logic domain thường xuyên, nên xem lại thiết kế method polymorphic hoặc service dispatch để không phải unproxy ở mọi call site.

### 11.4. Adapter cho code legacy

Một adapter có thể unwrap entity tại ranh giới với thư viện legacy, sau đó không cho proxy/entity rò rỉ ra tầng khác. Đây là cách cô lập Hibernate-specific API vào một vị trí dễ kiểm soát.

## 12. Khi nào không nên unproxy?

Không cần unproxy chỉ để đọc scalar property:

```java
String name = department.getName();
```

Hibernate có thể tự initialize proxy khi cần.

Không cần unproxy để lấy identifier nếu API chuẩn hoặc proxy metadata đã đủ:

```java
Long id = department.getId();
```

Không nên unproxy chỉ để gọi `toString()`, log hoặc serialize entity. Các method này có thể duyệt association lazy, gây N+1 hoặc lỗi khi session đóng.

Không nên unproxy mọi association trong vòng lặp:

```java
for (Employee employee : employees) {
    Department department =
        Hibernate.unproxy(employee.getDepartment());

    System.out.println(department.getName());
}
```

Nếu mỗi proxy được tải riêng, đây vẫn có thể là N+1. `@BatchSize`, fetch join, entity graph hoặc DTO query có thể là giải pháp phù hợp hơn.

Không nên unproxy chỉ để so sánh hai entity. Hãy thiết kế `equals()`/`hashCode()` proxy-aware; không tải toàn bộ entity chỉ để so ID.

## 13. Lấy identifier mà không cần unproxy

Trong Jakarta Persistence, có API chuẩn:

```java
import jakarta.persistence.PersistenceUnitUtil;

PersistenceUnitUtil util =
    emf.getPersistenceUnitUtil();

Object identifier = util.getIdentifier(entity);
```

API này hữu ích khi code cần identifier mà không phụ thuộc trực tiếp Hibernate.

Với Hibernate proxy, identifier thường đã có trong lazy initializer. Có thể truy cập qua Hibernate SPI:

```java
import org.hibernate.proxy.HibernateProxy;

if (entity instanceof HibernateProxy proxy) {
    Object id = proxy.getHibernateLazyInitializer().getIdentifier();
}
```

Đây là API Hibernate-specific/low-level. Chỉ dùng khi có lý do rõ ràng và kiểm tra version.

Không nên truy cập field ID bằng reflection hoặc ép kiểu proxy subclass để lấy ID. Identifier accessor/API chuyên dụng giữ code rõ ràng và ít phụ thuộc chi tiết proxy được sinh.

### 13.1. Identifier không phải concrete class

Biết ID `10` không cho biết entity là `CardPayment` hay `BankPayment`. Nếu cần type, phải dùng metadata/type API phù hợp hoặc tải entity khi concrete type chưa biết.

### 13.2. Không nhầm identifier với existence check

Một proxy có thể chứa identifier dù hàng database không tồn tại. Lấy ID thành công không chứng minh entity có hàng hợp lệ. Muốn kiểm tra existence, dùng `find()` hoặc truy vấn/constraint phù hợp.

## 14. `PersistenceUnitUtil.isLoaded()` và `Hibernate.isInitialized()`

Jakarta Persistence có:

```java
boolean loaded =
    emf.getPersistenceUnitUtil().isLoaded(entity);
```

và:

```java
boolean departmentLoaded =
    emf.getPersistenceUnitUtil().isLoaded(entity, "department");
```

Hibernate cung cấp:

```java
boolean initialized = Hibernate.isInitialized(entity);
```

và:

```java
boolean employeesInitialized =
    Hibernate.isInitialized(department.getEmployees());
```

Hai nhóm API có mục tiêu gần nhau nhưng scope khác nhau:

- `PersistenceUnitUtil.isLoaded()` là API chuẩn để kiểm tra load state theo entity/attribute.
- `Hibernate.isInitialized()` là Hibernate API áp dụng cho proxy và persistent collection.
- `isLoaded()` không unwrap object.
- `isInitialized()` không trả entity class.
- Kiểm tra load state không tự load dữ liệu.

Ví dụ:

```java
Department reference = em.getReference(Department.class, 10L);

System.out.println(Hibernate.isInitialized(reference));
// Có thể false.

System.out.println(Hibernate.isInitialized(
    reference.getEmployees()
));
// Việc lấy collection reference có thể không initialize collection;
// truy cập size/iterate mới có thể load.
```

Không gọi getter có side effect initialize chỉ để truyền object vào `isLoaded()` nếu mục tiêu là quan sát trạng thái ban đầu. Hãy giữ reference/attribute riêng và kiểm tra theo API phù hợp.

## 15. Proxy và bytecode enhancement không giống nhau

Hibernate có thể hỗ trợ lazy loading bằng **subclass proxy** hoặc **bytecode enhancement**.

### 15.1. Subclass proxy

Proxy là một lớp Java được sinh ra, thường kế thừa entity class và override các method có thể intercept:

```text
Department
    ↑
Department$HibernateProxy$...
```

Đặc điểm:

- `getClass()` có thể trả subclass proxy.
- `instanceof Department` thường vẫn true.
- Lazy initializer giữ identifier và session reference.
- Gọi method cần state có thể initialize proxy.
- Class/method `final` có thể hạn chế khả năng subclass proxy/interception.

### 15.2. Bytecode-enhanced entity

Với bytecode enhancement, Hibernate có thể thêm interception vào chính class entity để hỗ trợ lazy attribute loading hoặc lazy state:

```text
Department instance
  ├─ runtime class: Department
  └─ enhanced interception state
```

Trong trường hợp này, runtime class có thể vẫn là `Department.class`; không nhất thiết có subclass proxy để unproxy.

`Hibernate.unproxy(entity)` trên một object không phải Hibernate proxy sẽ trả lại object đó. Điều đó **không có nghĩa mọi lazy attribute bên trong đã initialized**.

### 15.3. Không dùng `getClass()` để phát hiện mọi hình thức lazy loading

```java
entity.getClass() == Department.class
```

không chứng minh entity đã được load đầy đủ. Bytecode-enhanced entity có thể giữ lazy attribute dù runtime class chính là entity class.

Muốn biết một attribute đã loaded hay chưa, dùng `PersistenceUnitUtil.isLoaded(entity, "attribute")` hoặc API Hibernate tương ứng.

## 16. Ảnh hưởng của `final` và method interception

Subclass proxy cần tạo một subclass của entity. Vì vậy một entity class `final` không thể được subclass theo cơ chế proxy thông thường; method `final` cũng không thể bị override để intercept theo cách đó.

Điều này không có nghĩa mọi entity có `final` đều không thể lazy-load trong mọi cấu hình. Bytecode enhancement có cơ chế khác và các chi tiết phụ thuộc Hibernate version/build.

Nguyên tắc:

- Không đánh dấu entity class `final` nếu kiến trúc proxy subclass cần kế thừa.
- Hạn chế `final` trên method cần interception khi dùng subclass proxies.
- Nếu dự án dùng enhancement, kiểm tra cấu hình build plugin/agent và test lazy attributes thực tế.
- Đừng thêm `final` chỉ để cố làm entity “bất biến” mà không hiểu persistence provider cần can thiệp thế nào.

## 17. `unproxy()` và equals/hashCode

Một lỗi thường gặp là so sánh:

```java
if (a.getClass() != b.getClass()) {
    return false;
}
```

Nếu `a` là entity thật và `b` là proxy subclass của cùng entity, hai runtime class có thể khác nhau.

Không nên unproxy cả hai chỉ để sửa equality, vì thao tác đó có thể initialize entity và phát SQL trong `HashSet.contains()` hoặc `Map.get()` — một nơi rất khó dự đoán chi phí.

Với Hibernate, có thể lấy persistent class cho proxy qua lazy initializer:

```java
import org.hibernate.proxy.HibernateProxy;

static Class<?> persistentClass(Object entity) {
    if (entity instanceof HibernateProxy proxy) {
        return proxy.getHibernateLazyInitializer()
                    .getPersistentClass();
    }
    return entity.getClass();
}
```

Helper này lấy **mapped class mà proxy được tạo cho** mà không cần gọi getter business data. Trong inheritance hierarchy polymorphic, đây không nhất thiết là concrete subtype cuối cùng nếu proxy chưa biết subtype; cần phân biệt declared/mapped proxy type với actual concrete type.

Một `equals()` dựa trên ID còn cần xử lý:

- Hai entity transient có ID null không được mặc nhiên bằng nhau.
- ID phải ổn định sau khi entity được đưa vào `HashSet`/`HashMap`.
- Entity type phải được so sánh theo policy nhất quán với inheritance.
- Không duyệt association lazy hoặc collection mutable trong equality.
- Cả hai chiều `entity.equals(proxy)` và `proxy.equals(entity)` phải đúng hợp đồng Java.

Nếu chỉ cần kiểm tra subtype thực cho một use case, hãy làm tại service boundary trong transaction; đừng để `equals()` tự initialize proxy.

## 18. Unproxy trong DTO mapping và serialization

Entity/proxy là object thuộc persistence layer. Trả trực tiếp ra JSON có thể dẫn đến:

- Serializer gọi getter lazy và phát SQL ngoài ý muốn.
- Vòng lặp hai chiều `Department.employees[*].department`.
- `LazyInitializationException` sau khi session đóng.
- Runtime proxy class hoặc Hibernate metadata lọt vào JSON.
- N+1 khi serializer truy cập nhiều association.

Unproxy không giải quyết đầy đủ những vấn đề này:

```java
Department actual = Hibernate.unproxy(department);
return objectMapper.writeValueAsString(actual);
```

Nếu `actual.getEmployees()` chưa initialized, serializer vẫn có thể kích hoạt lazy load hoặc lỗi.

Cách rõ ràng hơn là ánh xạ DTO trong transaction:

```java
public record DepartmentDto(
    Long id,
    String name,
    List<String> employeeNames
) {}

@Transactional(readOnly = true)
public DepartmentDto getDepartment(long id) {
    Department department = repository.findById(id)
        .orElseThrow();

    List<String> employeeNames = department.getEmployees()
        .stream()
        .map(Employee::getFullName)
        .toList();

    return new DepartmentDto(
        department.getId(),
        department.getName(),
        employeeNames
    );
}
```

Đoạn này chủ động truy cập collection trong transaction; cần fetch plan phù hợp nếu danh sách lớn. DTO tách contract API khỏi proxy và lifecycle Hibernate.

## 19. Unproxy và N+1 SELECT

Giả sử có 100 employee, mỗi employee tham chiếu một department lazy:

```java
for (Employee employee : employees) {
    Department department =
        Hibernate.unproxy(employee.getDepartment());

    System.out.println(department.getName());
}
```

Nếu mỗi department proxy chưa initialized và batch fetching không được cấu hình, vòng lặp có thể phát nhiều SELECT.

Unproxy **không phải batch operation**. Nó xử lý từng object được truyền vào. Để giảm N+1, cân nhắc:

```java
@BatchSize(size = 16)
@Entity
public class Department {
    // ...
}
```

hoặc:

- `JOIN FETCH` khi use case luôn cần association.
- Entity Graph cho fetch plan theo truy vấn.
- DTO projection khi chỉ cần vài cột.
- `FetchMode.SUBSELECT` cho collection role phù hợp.
- Batch fetching cho nhóm proxy/collection lazy.

Chọn chiến lược dựa trên dữ liệu cần và pagination; đừng unproxy hàng loạt rồi cho rằng Hibernate tự gom SQL.

## 20. Dùng Hibernate SPI `LazyInitializer` khi thật sự cần

Nếu cần thông tin thấp cấp về proxy, Hibernate có:

```java
if (entity instanceof HibernateProxy proxy) {
    var initializer = proxy.getHibernateLazyInitializer();

    Class<?> mappedType = initializer.getPersistentClass();
    Object id = initializer.getIdentifier();
    boolean uninitialized = initializer.isUninitialized();
}
```

Các method cụ thể có thể thay đổi theo Hibernate version; đây là API gắn với proxy SPI, không phải Jakarta Persistence portable.

`LazyInitializer` hữu ích cho framework integration hoặc diagnostic code cần đọc identifier/mapped class/trạng thái proxy mà không gọi getter business.

Không nên rải `HibernateProxy` checks khắp domain model. Đóng chúng trong một utility hoặc adapter ở persistence boundary để code nghiệp vụ không phụ thuộc implementation detail.

### 20.1. Không lấy implementation trực tiếp nếu chỉ cần metadata

Nếu chỉ cần:

- ID: dùng `PersistenceUnitUtil.getIdentifier()` hoặc proxy initializer khi cần Hibernate-specific.
- Load state: dùng `PersistenceUnitUtil.isLoaded()`/`Hibernate.isInitialized()`.
- Mapped class: dùng metadata/type API phù hợp.
- Concrete implementation: dùng `Hibernate.unproxy()` trong context hợp lệ.

Mỗi mục tiêu có API hẹp hơn. Chọn đúng API giúp tránh vô tình khởi tạo entity.

## 21. Lựa chọn API theo tình huống

| Nhu cầu | Lựa chọn thường phù hợp | SQL side effect cần lưu ý |
| --- | --- | --- |
| Đọc scalar property | Gọi getter trong session | Có thể initialize proxy |
| Lấy identifier | `getId()` hoặc `PersistenceUnitUtil.getIdentifier()` | Thường không cần load toàn state; xác minh provider/mapping |
| Kiểm tra proxy đã initialized | `Hibernate.isInitialized()` | Không cần initialize để kiểm tra |
| Kiểm tra attribute đã loaded | `PersistenceUnitUtil.isLoaded(entity, name)` | API kiểm tra trạng thái |
| Lấy mapped/concrete class chính xác | `Hibernate.getClass()` | Có thể initialize |
| Cố lấy class không initialize | `Hibernate.getClassLazy()` | Có thể initialize nếu không thể xác định |
| Lấy implementation thật | `Hibernate.unproxy()` | Initialize proxy nếu cần |
| Chủ động initialize mà giữ reference | `Hibernate.initialize()` | Có thể phát SELECT |
| Xử lý dữ liệu cho REST/API | DTO projection/mapping | Fetch plan được kiểm soát |
| So sánh entity/proxy | Proxy-aware equality | Tránh unproxy trong equals/hashCode |
| Chuyển dữ liệu qua session boundary | DTO hoặc ID rồi load lại | Không truyền proxy chưa initialized |

## 22. Ví dụ tổng hợp: kiểm tra class và lấy implementation

```java
import org.hibernate.Hibernate;

import jakarta.persistence.EntityManager;

try (EntityManager em = emf.createEntityManager()) {
    Department reference = em.getReference(Department.class, 10L);

    boolean initializedBefore = Hibernate.isInitialized(reference);

    Class<?> runtimeClass = reference.getClass();
    Class<?> entityClass = Hibernate.getClass(reference);

    Department actual = Hibernate.unproxy(
        reference,
        Department.class
    );

    boolean initializedAfter = Hibernate.isInitialized(actual);

    System.out.println("initialized before = " + initializedBefore);
    System.out.println("runtime class = " + runtimeClass.getName());
    System.out.println("entity class = " + entityClass.getName());
    System.out.println("actual class = " + actual.getClass().getName());
    System.out.println("initialized after = " + initializedAfter);
}
```

Đây là ví dụ quan sát, không phải assertion rằng mọi dòng đều có cùng SQL behavior:

- `getReference()` có thể trả proxy chưa initialized.
- `getClass()` của Java chỉ cho runtime class và không tự yêu cầu load state.
- `Hibernate.getClass()` có thể initialize proxy để xác định class.
- `unproxy()` lấy implementation và có thể dùng lại trạng thái đã initialized ở bước trước.
- Nếu `getClass()` hoặc `unproxy()` đã khởi tạo proxy, dòng sau không phát thêm SELECT cho cùng entity.

Nếu mục tiêu chỉ là lấy implementation, có thể không cần gọi cả `Hibernate.getClass()` và `unproxy()`; ví dụ này cố ý trình bày từng API để quan sát sự khác nhau.

## 23. Kiểm thử proxy và unproxy

Cần integration test với Hibernate thực, vì unit test tạo `new Department(...)` không tạo Hibernate proxy.

Giả định fixture đã có `EntityManagerFactory emf`, bảng `departments` và hàng ID `10`.

### 23.1. Test `getReference()` và unproxy trong session mở

```java
import jakarta.persistence.EntityManager;
import org.hibernate.Hibernate;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class UnproxyIntegrationTest {

    private final EntityManagerFactory emf;

    UnproxyIntegrationTest(EntityManagerFactory emf) {
        this.emf = emf;
    }

    @Test
    void unproxyReturnsImplementationForDepartmentReference() {
        try (EntityManager em = emf.createEntityManager()) {
            Department reference =
                em.getReference(Department.class, 10L);

            Department actual =
                Hibernate.unproxy(reference, Department.class);

            assertNotNull(actual);
            assertEquals(10L, actual.getId());
            assertTrue(Hibernate.isInitialized(actual));
            assertEquals("Department", Hibernate.getClass(actual).getSimpleName());
        }
    }
}
```

Đây là test body minh họa; cần cấu hình JUnit fixture để tạo/cấp `EntityManagerFactory`, seed dữ liệu và đóng factory. JUnit 5 không tự inject `EntityManagerFactory` trong constructor nếu không có extension phù hợp.

Assertion tên class `"Department"` chỉ phù hợp fixture entity không có subtype. Với inheritance, hãy assert theo policy concrete/mapped type thực tế.

### 23.2. Test proxy runtime class có thể khác entity class

```java
try (EntityManager em = emf.createEntityManager()) {
    Department reference =
        em.getReference(Department.class, 10L);

    Class<?> runtimeType = reference.getClass();
    Class<?> mappedType = Hibernate.getClass(reference);

    assertNotEquals(Department.class, runtimeType);
    assertEquals(Department.class, mappedType);
}
```

Không dùng test này như cam kết mọi cấu hình đều tạo subclass proxy. Bytecode enhancement hoặc entity đã có trong persistence context có thể khiến `getReference()` trả representation khác. Hãy xác nhận proxy thực sự chưa initialized trước khi assert runtime class khác.

### 23.3. Test detached uninitialized proxy

Một kịch bản:

```java
Department reference;

try (EntityManager em = emf.createEntityManager()) {
    reference = em.getReference(Department.class, 10L);
}

// Nếu reference vẫn uninitialized, unproxy có thể thất bại vì session đã đóng.
```

Không nên assert chính xác một exception cho mọi enhancement/provider configuration. Test nên xác minh điều kiện tiền đề `!Hibernate.isInitialized(reference)` trước khi kiểm tra behavior detached, và chạy trên đúng Hibernate version/fixture.

### 23.4. Test lazy association vẫn chưa initialized sau unproxy

```java
Department reference = em.getReference(Department.class, 10L);
Department actual = Hibernate.unproxy(reference);

assertTrue(Hibernate.isInitialized(actual));

// Nếu employees là LAZY và chưa được truy cập:
assertFalse(Hibernate.isInitialized(actual.getEmployees()));
```

Để test không tự kích hoạt collection khi gọi getter, lấy reference và kiểm tra load state ngay; việc gọi `getEmployees()` thường trả persistent collection wrapper nhưng không nhất thiết initialize nó. Xác nhận bằng Hibernate Statistics/SQL logging nếu test phụ thuộc chính xác behavior.

## 24. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `entity.getClass() == Entity.class` trả false | Object là subclass proxy | Dùng `Hibernate.getClass()` hoặc `getClassLazy()` phù hợp |
| `unproxy()` ném `LazyInitializationException` | Proxy chưa initialized, session đã đóng | Unproxy/load trong context mở hoặc load lại bằng ID |
| Unproxy làm xuất hiện SELECT | Proxy phải được initialize để lấy implementation | Chấp nhận rõ side effect hoặc tránh cần implementation |
| Sau unproxy vẫn lỗi khi truy cập collection | Association vẫn lazy, unproxy không tải graph | Fetch collection/DTO trong transaction |
| `getClassLazy()` vẫn phát SQL | Concrete subtype chưa biết nếu không đọc DB | Thiết kế type dispatch hoặc chấp nhận load |
| `instanceof BaseEntity` true nhưng `getClass()` khác | Proxy subclass vẫn là subtype của base | Dùng persistent type API khi so class chính xác |
| Entity enhanced có runtime class chuẩn nhưng field vẫn lazy | Enhancement intercepts attributes thay vì subclass proxy | Dùng load-state API, không dựa `getClass()` |
| Serialize entity gây N+1 | Serializer gọi getter lazy | Map sang DTO với fetch plan rõ |
| `equals()` phát SQL | Equality gọi getter/`Hibernate.getClass()`/unproxy không phù hợp | Dùng ID/type metadata proxy-aware, không load graph |
| Unproxy mọi phần tử vẫn chậm | Mỗi proxy khởi tạo riêng, gây N+1 | Batch fetching/fetch join/entity graph/DTO |
| `getReference()` không báo entity không tồn tại | Proxy chưa được initialize | Dùng `find()` nếu cần existence check |
| `HibernateProxy` cast thất bại | Object không phải subclass proxy hoặc dùng enhancement | Dùng API chung `Hibernate`/JPA, kiểm tra representation thực |

## 25. Những hiểu lầm cần tránh

**“Proxy là một entity khác.”** Không. Proxy đại diện cho persistent identity của entity được ánh xạ.

**“`getClass()` luôn trả lớp entity.”** Không. Với subclass proxy, nó có thể trả lớp proxy được sinh.

**“`Hibernate.getClass()` không bao giờ truy vấn database.”** Không. Nó có thể initialize proxy để xác định lớp thực.

**“`getClassLazy()` bảo đảm tuyệt đối không initialize.”** Không. Nó cố tránh initialization khi có thể; polymorphic type chưa biết có thể cần tải.

**“Unproxy chỉ bỏ wrapper mà không SQL.”** Không. Lấy implementation có thể yêu cầu khởi tạo proxy và phát SELECT.

**“Unproxy xong mọi quan hệ đã được load.”** Không. Association/collection lazy và lazy basic attributes vẫn có thể chưa initialized.

**“`Hibernate.initialize()` trả về entity thật.”** Không. API trả `void`; nó yêu cầu initialize object được truyền vào.

**“Unproxy giải quyết `LazyInitializationException` sau khi session đóng.”** Không. Nếu proxy cần load nhưng context đã đóng, unproxy cũng không thể tự tải dữ liệu.

**“Có identifier nghĩa là hàng database tồn tại.”** Không. Proxy có thể giữ ID mà chưa kiểm tra hàng.

**“Bytecode-enhanced entity luôn có runtime class khác.”** Không. Enhancement có thể giữ nguyên class entity và intercept field/property access.

**“Chỉ cần unproxy trước JSON serialization.”** Không. Association bên trong vẫn có thể lazy; DTO là ranh giới API ổn định hơn.

**“Unproxy trong `equals()` là an toàn.”** Không. Nó có thể phát SQL khi hash collection đang hoạt động, gây N+1 hoặc lỗi detached proxy.

## 26. Quy trình lựa chọn khi cần làm việc với thực thể thực

Trước khi dùng một API unproxy/type, xác định rõ mục tiêu:

**Bước 1 — Chỉ cần ID?**

Dùng getter identifier hoặc `PersistenceUnitUtil.getIdentifier()`. Không tải implementation nếu không cần.

**Bước 2 — Chỉ cần biết object đã load chưa?**

Dùng `PersistenceUnitUtil.isLoaded()` hoặc `Hibernate.isInitialized()`. Đây là thao tác kiểm tra trạng thái, không phải unproxy.

**Bước 3 — Chỉ cần mapped/concrete class?**

Cân nhắc `Hibernate.getClassLazy()` nếu version hỗ trợ và tránh initialization là quan trọng. Dùng `Hibernate.getClass()` khi cần type chính xác và chấp nhận khả năng load.

**Bước 4 — Cần gọi API của implementation?**

Dùng `Hibernate.unproxy()` trong persistence context còn mở. Nếu có thể, thiết kế method polymorphic trên base type để không phải cast.

**Bước 5 — Cần dữ liệu cho API hoặc serialization?**

Map sang DTO trong transaction với fetch plan rõ ràng. Không trả proxy ra tầng web.

**Bước 6 — Cần làm việc với hàng loạt proxy?**

Không unproxy từng object trong loop mà chưa đo. Cân nhắc batch fetching, fetch join, entity graph hoặc projection.

**Bước 7 — Có inheritance/polymorphic association?**

Phân biệt declared type, mapped proxy class và concrete subtype. Kiểm tra behavior với đúng strategy và Hibernate version.

## 27. Tài liệu tham khảo chính thức

- [Hibernate ORM User Guide — Proxy fetching](https://docs.hibernate.org/stable/orm/userguide/html_single/#fetching-proxies): lazy proxy, proxy initialization và fetching behavior.
- [Hibernate ORM Javadoc — `Hibernate`](https://docs.hibernate.org/stable/orm/javadocs/org/hibernate/Hibernate.html): `getClass`, `getClassLazy`, `unproxy`, `initialize`, `isInitialized` và load-state helpers.
- [Hibernate ORM Javadoc — `HibernateProxy`](https://docs.hibernate.org/stable/orm/javadocs/org/hibernate/proxy/HibernateProxy.html): API nhận diện proxy và lấy lazy initializer.
- [Hibernate ORM Javadoc — `LazyInitializer`](https://docs.hibernate.org/stable/orm/javadocs/org/hibernate/proxy/LazyInitializer.html): identifier, persistent class, implementation và trạng thái khởi tạo của proxy.
- [Hibernate ORM User Guide — Bytecode enhancement](https://docs.hibernate.org/stable/orm/userguide/html_single/# Bytecode-enhancement): lazy attribute loading và các đặc tính của enhancement; đường dẫn anchor có thể thay đổi theo phiên bản tài liệu.
- [Jakarta Persistence 3.2 — `PersistenceUnitUtil`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/persistenceunitutil.html): identifier và load-state utilities ở cấp chuẩn.
- [Jakarta Persistence 3.2 — `EntityManager.getReference`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/entitymanager.html): semantics của reference tới entity theo primary key.
- [Hibernate ORM User Guide — Fetching](https://docs.hibernate.org/stable/orm/userguide/html_single/#fetching): lazy/eager, batch fetching, join fetching và N+1.

Các method Hibernate-specific có thể khác giữa Hibernate 5, 6 và 7. Đặc biệt, hãy kiểm tra sự hiện diện/semantics của `getClassLazy()` trong Javadoc đúng version. API Jakarta Persistence như `PersistenceUnitUtil` có tính portable hơn nhưng không cung cấp toàn bộ khả năng unproxy của Hibernate.

## Kết luận

Proxy là representation lazy của entity, nên **runtime class không nhất thiết là mapped entity class**. `Object.getClass()` có thể trả subclass proxy; `Hibernate.getClass()` xác định class phía sau proxy nhưng có thể initialize; `Hibernate.getClassLazy()` cố lấy type mà không initialize khi có thể; còn `Hibernate.unproxy()` trả implementation thực và có thể phát SELECT nếu proxy chưa được tải.

Chỉ unproxy khi code thực sự cần implementation, và thực hiện trong persistence context phù hợp. Unproxy không detach, không commit, không tải toàn bộ association graph và không tự chữa N+1 hoặc `LazyInitializationException` ngoài session. Với identifier, load state, type metadata và DTO mapping, hãy dùng API hẹp hơn tương ứng. Khi có inheritance hoặc bytecode enhancement, kiểm thử trên đúng Hibernate version để phân biệt **runtime proxy class, mapped type và concrete entity type** trước khi viết logic phụ thuộc kiểu.

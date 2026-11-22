# Proxy, kế thừa và nguy cơ so sánh kiểu thực thể không đúng trong Hibernate

Trong Hibernate ORM, **danh tính đối tượng** (*object identity*) và **kiểu của đối tượng đang cầm trong tay** là hai vấn đề liên quan nhưng khác nhau. Một entity có thể được Hibernate đại diện bằng **proxy** để trì hoãn truy vấn SQL. Proxy mang cùng định danh ORM với bản ghi thật, nhưng **lớp Java runtime của proxy không nhất thiết là lớp entity được lưu trong database**. Sự khác biệt ấy đặc biệt quan trọng khi entity có **kế thừa** (`SINGLE_TABLE`, `JOINED`, `TABLE_PER_CLASS`) và mã ứng dụng dùng `getClass()`, `instanceof`, `equals()` hoặc ép kiểu.

Nếu xử lý không đúng, ứng dụng có thể từ chối một entity hợp lệ, kết luận nhầm rằng hai entity khác nhau, thực thi sai nhánh nghiệp vụ, tạo key không nhất quán trong `HashSet`/`HashMap` hoặc kích hoạt SQL ngoài transaction rồi gặp `LazyInitializationException`.

Bài này dùng thuật ngữ và API của **Jakarta Persistence** và **Hibernate ORM 6.x**, với ví dụ Hibernate 6.6. Proxy, bytecode enhancement và cách Hibernate giải quyết subtype có thể khác nhau theo phiên bản và cấu hình. Không nên biến một hành vi quan sát được trong một lần chạy thành cam kết cho mọi cách lấy entity.

## 1. Bốn khái niệm cần phân biệt trước khi so sánh entity

| Khái niệm | Nội dung | Ví dụ |
| --- | --- | --- |
| **Java reference identity** | Hai biến có trỏ tới đúng **cùng một object** trong heap hay không? Kiểm tra bằng `==`. | `a == b`. |
| **Persistence identity** | Entity được xác định bởi **entity identity/mapping và ID** trong phạm vi persistence model. | `Payment` với ID 42 trong một persistence unit. |
| **Java runtime class** | Lớp mà JVM nhìn thấy tại thời điểm chạy, qua `obj.getClass()`. | `Payment$HibernateProxy$...`. |
| **Concrete persistent entity type** | Loại entity thực sự được database/mapping đại diện khi tải đầy đủ. | `CardPayment`, dù biến ban đầu có kiểu `Payment`. |

Một persistence context (first-level cache) duy trì **identity map**: trong cùng `Session`/`EntityManager`, entity có cùng persistent identity thường được gắn với một object được quản lý tương ứng. Khi truy vấn cùng ID qua nhiều cách khác nhau, Hibernate cố duy trì tính nhất quán của identity trong context đó.

Tuy nhiên:

- **Hai session khác nhau** có thể tải cùng một hàng thành **hai đối tượng Java khác nhau**. Vì vậy `==` không thể làm tiêu chuẩn nhận diện entity xuyên session.
- **Proxy** có thể đại diện cho entity chưa được khởi tạo. `getClass()` trên proxy phản ánh lớp proxy do Hibernate tạo, không nhất thiết phản ánh kiểu subclass lưu trong DB.
- **ID bằng nhau** chưa chắc là cùng một entity nếu hai ID thuộc hai loại entity không liên quan hoặc hai persistence unit/tenant khác nhau.
- **Kế thừa** khiến việc xác định “cùng kiểu entity” cần hiểu cả *lớp Java* lẫn *gốc của entity hierarchy*.

Ví dụ:

~~~text
Session A                         Session B
  CardPayment#42 (managed)         CardPayment#42 (managed)
         |                                |
   Java object A                     Java object B
         |                                |
         +----- cùng hàng database ------+
~~~

`objectA == objectB` có thể là `false`. Nhưng nếu cùng database, cùng tenant, cùng mapping và cùng ID, hai object có thể biểu diễn **cùng một entity về mặt persistence**.

## 2. Proxy là gì và vì sao Hibernate tạo proxy?

Giả sử một đơn hàng có quan hệ tới payment:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class Order {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "payment_id")
    private Payment payment;

    protected Order() {}

    public Payment getPayment() {
        return payment;
    }
}
~~~

Khi tải `Order`, Hibernate có thể biết `payment_id = 42` từ hàng `orders` mà chưa cần truy vấn bảng payment. Nó có thể tạo một object đại diện:

~~~text
Order (managed)
   payment ----> Payment proxy (id = 42, chưa đọc dữ liệu Payment)
                       |
                       +---- khi cần: SELECT ... FROM payments ...
~~~

Proxy thường được tạo bằng cơ chế tạo subclass/interception. Object proxy giữ thông tin như entity name, identifier và liên kết tới persistence context để **khởi tạo entity thực sự khi một thao tác cần trạng thái**. Không nên xem proxy như một bản sao đầy đủ của entity.

Những lợi ích phổ biến:

1. Tránh tải ngay mọi association khi không cần.
2. Cho phép Hibernate biểu diễn tham chiếu tới entity bằng ID, chẳng hạn qua `getReference()`.
3. Hỗ trợ chuỗi quan hệ lazy theo fetch plan và giảm truy vấn thừa khi ứng dụng được thiết kế đúng.

Nhưng **`LAZY` không bảo đảm mọi thao tác luôn sử dụng subclass proxy**. Hibernate có nhiều cơ chế nạp dữ liệu, bao gồm proxy, bytecode enhancement, các chiến lược fetch khác và những trường hợp provider phải tải eager. Cách triển khai có thể thay đổi theo mapping/phiên bản.

### 2.1. Tạo tham chiếu qua `getReference()`

~~~java
Payment reference =
        entityManager.getReference(Payment.class, 42L);
~~~

`getReference()` thường cho phép tạo tham chiếu tới ID 42 **mà chưa cần truy vấn để xác nhận hàng tồn tại ngay**. Vì vậy:

- Không coi `getReference()` là phép kiểm tra tồn tại.
- Khi truy cập trạng thái cần tải, Hibernate có thể truy vấn database và báo `EntityNotFoundException` nếu bản ghi không tồn tại.
- Nếu `EntityManager`/`Session` đã đóng trước khi proxy được khởi tạo, việc truy cập thuộc tính lazy có thể dẫn tới `LazyInitializationException`.
- Nếu persistence context đã có entity managed phù hợp, provider có thể trả chính đối tượng đó thay vì tạo proxy mới.

Một ví dụ minh họa việc quan sát class:

~~~java
Payment reference =
        entityManager.getReference(Payment.class, paymentId);

System.out.println(reference.getClass().getName());
~~~

Kết quả **có thể** là tên lớp proxy do Hibernate sinh, ví dụ có phần chứa `HibernateProxy`. Đây không phải API ổn định để phân tích tên lớp hoặc xác định subclass; tên thực tế không được cam kết.

### 2.2. Proxy không nhất thiết là entity chưa tồn tại trong memory

Nếu entity đã được tải và quản lý trong session, Hibernate có thể tái sử dụng instance đó cho tham chiếu cùng persistent identity. Nếu chưa tải, proxy có thể được giữ trong persistence context và được khởi tạo về sau. Vì vậy một test chạy khi entity đã có trong first-level cache có thể khác test chạy trong session sạch.

Nếu muốn quan sát tác dụng của lazy loading, hãy thử trong **một persistence context mới**, với logging SQL phù hợp, thay vì chỉ nhìn `getClass()` một lần rồi kết luận cơ chế Hibernate luôn tạo proxy.

## 3. Vấn đề cốt lõi: proxy của lớp cha và subclass thực tế

Giả sử entity hierarchy:

~~~mermaid
flowchart TD
    P["Payment (@Entity, abstract)"]
    C["CardPayment (@Entity)"]
    B["BankTransferPayment (@Entity)"]
    P -->|"extends"| C
    P -->|"extends"| B
~~~

Ví dụ entity (các constructor/getter không liên quan được rút gọn):

~~~java
import jakarta.persistence.*;

@Entity
@Inheritance(strategy = InheritanceType.JOINED)
@Table(name = "payments")
public abstract class Payment {
    @Id
    private Long id;

    public Long getId() {
        return id;
    }
}

@Entity
@Table(name = "card_payments")
public class CardPayment extends Payment {
    private String cardLast4;

    public String getCardLast4() {
        return cardLast4;
    }
}

@Entity
@Table(name = "bank_transfer_payments")
public class BankTransferPayment extends Payment {
    private String bankReference;
}
~~~

Trong `JOINED`, hàng `payments.id = 42` có thể thuộc `CardPayment`, được xác định bởi hàng tương ứng ở bảng `card_payments`. Nhưng khi một code path yêu cầu:

~~~java
Payment reference =
        entityManager.getReference(Payment.class, 42L);
~~~

Hibernate chỉ được yêu cầu tạo **tham chiếu tới `Payment` theo ID**. Trước khi kiểm tra dữ liệu subclass, proxy tạo cho lớp cha **không có cơ sở chắc chắn để giả làm `CardPayment` ngay từ đầu**.

~~~text
Database:
  payments(id = 42)
  card_payments(payment_id = 42)   → concrete entity CardPayment

Java:
  Payment reference = getReference(Payment.class, 42)
                     └── có thể là proxy kế thừa Payment
                         chứ không kế thừa CardPayment
~~~

### 3.1. `getClass()` có thể chỉ ra lớp proxy

~~~java
Payment reference =
        entityManager.getReference(Payment.class, 42L);

boolean exactType = reference.getClass() == CardPayment.class;
~~~

`exactType` có thể bằng `false` dù hàng 42 là CardPayment. Trong trường hợp proxy subclass của Payment, `reference.getClass()` là **lớp proxy runtime**, không phải `CardPayment.class`.

Ngay cả với một tham chiếu được khai báo cụ thể:

~~~java
CardPayment reference =
        entityManager.getReference(CardPayment.class, 42L);
~~~

`reference.getClass() == CardPayment.class` vẫn có thể là `false` vì proxy subclass của `CardPayment` có lớp runtime khác.

**Quy tắc:** không dùng `entity.getClass() == SomeEntity.class` để kiểm tra business type khi entity có thể là Hibernate proxy.

### 3.2. `instanceof` cũng có giới hạn khi lấy qua lớp cha

~~~java
Payment reference =
        entityManager.getReference(Payment.class, 42L);

if (reference instanceof CardPayment) {
    // Không chắc chạy dù DB chứa CardPayment#42.
}
~~~

Nếu proxy do Hibernate tạo **kế thừa `Payment`**, JVM biết object là một `Payment`, nhưng không thể xem nó là `CardPayment` nếu lớp proxy không kế thừa CardPayment. Kiểm tra `instanceof CardPayment` có thể trả `false`.

Đặc biệt, **việc khởi tạo dữ liệu bên trong một proxy không biến lớp Java runtime của object proxy thành subclass khác**. JVM không thay đổi superclass của một object đang tồn tại. Vì thế không nên suy ra rằng chỉ cần gọi một getter để khởi tạo proxy thì `instanceof CardPayment` trên chính biến proxy sẽ tự chuyển thành `true`.

Ngược lại, nếu Hibernate trả về trực tiếp entity thực tế (đã loaded hoặc cơ chế enhancement khác), `instanceof CardPayment` có thể là `true`. Hành vi không đồng nhất giữa các đường lấy dữ liệu chính là lý do logic nghiệp vụ không nên dựa vào kiểu runtime của một tham chiếu chưa được xử lý rõ ràng.

### 3.3. `instanceof Payment` có thể đúng mà chưa biết subtype

Với một proxy kế thừa `Payment`:

~~~java
boolean isPayment = reference instanceof Payment;      // Thường true.
boolean isCard = reference instanceof CardPayment;     // Không đáng tin để tìm subtype.
~~~

Đây không phải mâu thuẫn: `instanceof` của Java kiểm tra **quan hệ kế thừa trong JVM**, không đọc discriminator hay join các bảng để xác định **concrete persistent entity type**.

### 3.4. Kế thừa và “biết loại” qua các chiến lược mapping

| Inheritance strategy | Hibernate có thể tìm subtype từ đâu? | Lưu ý cho proxy |
| --- | --- | --- |
| `SINGLE_TABLE` | Cột discriminator hoặc cơ chế phân biệt tương ứng trên một bảng | Tham chiếu proxy theo root có thể được tạo trước khi đọc discriminator. |
| `JOINED` | Discriminator nếu cấu hình, hoặc sự tồn tại của hàng subclass/tổ hợp join | Nếu chỉ biết root ID, có thể cần truy vấn để xác định subtype thực. |
| `TABLE_PER_CLASS` | Bảng subclass cụ thể, kế hoạch query đa hình, cơ chế sinh ID | Nhận diện subclass và tính duy nhất ID trong hierarchy phải phù hợp mapping/DB. |
| `@MappedSuperclass` | Không phải entity root có thể truy vấn đa hình | Không dùng mapped superclass như một entity proxy root. |

Không có quy tắc “mọi `JOINED` luôn tạo proxy theo lớp gốc” hoặc “mọi `SINGLE_TABLE` tự biết subclass trước khi query”. Điều quyết định là **loại entity mà API được yêu cầu**, trạng thái persistence context, chiến lược fetch và cách Hibernate khởi tạo tham chiếu.

## 4. Khi cần biết concrete persistent type: công cụ Hibernate

Hibernate cung cấp các API chuyên biệt để làm việc với proxy. Chọn đúng công cụ theo mục tiêu, và lưu ý tác dụng phụ về truy vấn.

### 4.1. `Hibernate.getClass(entity)`

~~~java
import org.hibernate.Hibernate;

Payment reference =
        entityManager.getReference(Payment.class, paymentId);

Class<?> actualEntityClass = Hibernate.getClass(reference);

if (actualEntityClass == CardPayment.class) {
    // Đã xác định concrete entity type theo Hibernate.
}
~~~

`Hibernate.getClass(entity)` giải quyết vấn đề lớp proxy và trả về lớp entity thực sự. Nhưng **đối với proxy, phương thức này có thể buộc khởi tạo proxy**, dẫn tới truy vấn SQL. Hibernate ORM 6.x documentation mô tả tác dụng phụ khởi tạo này.

Hệ quả:

- Cần persistence context hoạt động nếu proxy chưa được khởi tạo.
- Nếu transaction/session đã đóng, thao tác có thể ném `LazyInitializationException`.
- Có thể tăng số query, đặc biệt khi gọi cho hàng trăm entity trong một collection.
- Không nên gọi `Hibernate.getClass` trong `hashCode()` hay logging `toString()` nếu không chủ ý chấp nhận lazy loading.

Đặt tên `getClass` rất giống `Object.getClass()` nhưng **không đồng nghĩa**: một bên đọc class của JVM object, một bên làm việc với entity type thực tế qua Hibernate.

### 4.2. `Hibernate.unproxy(entity)`

Khi cần dùng hành vi riêng của subtype, thay vì chỉ biết tên lớp, có thể lấy implementation từ proxy:

~~~java
Payment paymentRef =
        entityManager.getReference(Payment.class, paymentId);

Payment actual = (Payment) Hibernate.unproxy(paymentRef);

if (actual instanceof CardPayment card) {
    System.out.println(card.getCardLast4());
} else if (actual instanceof BankTransferPayment bank) {
    System.out.println(bank.getBankReference());
}
~~~

`Hibernate.unproxy` có thể phải khởi tạo proxy để trả về đối tượng entity thật. Do đó nên thực hiện **trong transaction hoặc một session mở** và theo fetch plan có chủ đích. Sau khi unproxy, `instanceof` trên object đã được giải proxy phản ánh subclass Java thực tế theo mapping đang dùng.

Một overload có kiểu trả về:

~~~java
CardPayment card =
        Hibernate.unproxy(paymentRef, CardPayment.class);
~~~

Nên dùng overload này khi **đã chắc chắn** entity là `CardPayment` hoặc đã kiểm tra loại. Nếu object thật không tương thích với kiểu yêu cầu, phép chuyển kiểu sẽ thất bại theo hợp đồng API. Nếu proxy trỏ tới ID không tồn tại, việc khởi tạo có thể gây exception truy xuất entity. Không dùng `unproxy` như cách “ép” bất kỳ Payment nào thành CardPayment.

### 4.3. `Hibernate.isInitialized(entity)` và `initialize(entity)`

~~~java
import org.hibernate.Hibernate;

boolean loaded = Hibernate.isInitialized(paymentRef);

if (!loaded) {
    Hibernate.initialize(paymentRef);
}
~~~

`isInitialized` giúp hỏi một proxy/collection có được khởi tạo chưa theo cơ chế Hibernate. `initialize` yêu cầu khởi tạo, và có thể thực thi SQL hoặc thất bại nếu không còn session phù hợp. **Khởi tạo** và **thay lớp Java runtime của proxy** là hai việc khác nhau; sau `initialize`, không dùng `reference instanceof CardPayment` như một phép xác định subtype đáng tin trong mọi trường hợp.

Nếu cần subtype thực tế, dùng `Hibernate.getClass` để nhận diện hoặc `Hibernate.unproxy` rồi mới `instanceof`.

### 4.4. `HibernateProxy` và `LazyInitializer`: không dùng nhầm lớp được khai báo

Một số ứng dụng kiểm tra:

~~~java
import org.hibernate.proxy.HibernateProxy;

if (paymentRef instanceof HibernateProxy proxy) {
    Class<?> mappedType =
            proxy.getHibernateLazyInitializer().getPersistentClass();
}
~~~

Đây là cách truy cập thông tin proxy ở mức Hibernate-specific. **`getPersistentClass()` có thể phản ánh lớp entity mà proxy được tạo theo đó**, ví dụ `Payment`, chứ không nhất thiết là concrete subclass `CardPayment` lưu trong DB. Trong một hierarchy, nếu Hibernate chưa đọc dữ liệu phân biệt subclass thì metadata proxy không có cách thần kỳ để xác nhận subclass.

Đoạn code trên có thể hữu ích khi làm việc với metadata proxy mà không muốn tự khởi tạo, nhưng **không thay thế `Hibernate.getClass`/`unproxy` nếu cần xác định concrete subtype**. Đồng thời nó gắn ứng dụng vào API Hibernate cụ thể thay vì Jakarta Persistence thuần.

### 4.5. Khi không cần biết subtype, đừng khởi tạo chỉ để phân loại

Nếu nghiệp vụ chỉ cần ID, loại tham chiếu gốc, hoặc cần phát một sự kiện chứa ID, có thể tránh truy vấn subtype:

~~~java
public record PaymentReference(Long paymentId) {}

PaymentReference referenceDto =
        new PaymentReference(order.getPayment().getId());
~~~

Với nhiều mapping proxy Hibernate mặc định, accessor của identifier thường có thể được xử lý mà không tải đầy đủ entity; **không nên xem đó là cam kết áp dụng cho mọi mapping/cấu hình JPA proxy compliance và phương thức getter**. Khi chỉ muốn lấy identifier của một entity/ref, Jakarta Persistence còn có `PersistenceUnitUtil.getIdentifier(entity)`; việc entity không thuộc persistence unit hoặc cách provider xử lý proxy phải được xem xét.

Quan trọng hơn: một DTO chứa ID không có trách nhiệm xác định subtype. Nếu cần subtype để thực hiện hành vi nghiệp vụ, hãy truy xuất nó ở tầng service trong transaction và trả kết quả phù hợp.

## 5. Sự cố thực tế: dùng `getClass()` để phân nhánh nghiệp vụ

Đoạn code sau có thể sai khi `payment` là proxy:

~~~java
public String describe(Payment payment) {
    if (payment.getClass() == CardPayment.class) {
        return "Thanh toán thẻ";
    }
    if (payment.getClass() == BankTransferPayment.class) {
        return "Chuyển khoản";
    }
    return "Không nhận diện được phương thức thanh toán";
}
~~~

Một `CardPayment` hợp lệ có thể rơi vào nhánh “không nhận diện” nếu tham chiếu mà service nhận là proxy của `Payment`.

Một phiên bản có chủ đích khi service đang nằm trong transaction:

~~~java
import org.hibernate.Hibernate;

public String describe(Payment payment) {
    Payment actual = (Payment) Hibernate.unproxy(payment);

    if (actual instanceof CardPayment) {
        return "Thanh toán thẻ";
    }
    if (actual instanceof BankTransferPayment) {
        return "Chuyển khoản";
    }
    return "Loại thanh toán khác";
}
~~~

Cách này **có thể tải SQL**; chỉ dùng khi thật sự cần phân biệt subtype trong ORM domain. Nếu logic xử lý subtype là hành vi vốn thuộc entity, có thể cân nhắc **đa hình bằng method override**:

~~~java
// Trong Payment:
public abstract String getPaymentKind();

// Trong CardPayment:
@Override
public String getPaymentKind() {
    return "CARD";
}

// Trong BankTransferPayment:
@Override
public String getPaymentKind() {
    return "BANK";
}
~~~

Một proxy khi gọi method cần trạng thái/hành vi của entity có thể được Hibernate khởi tạo trước khi chuyển đến implementation. Thiết kế này giúp mã ứng dụng không phải tự viết `if` theo class ở mọi nơi, nhưng **không xóa được vấn đề lazy loading**. Nếu gọi method sau khi session đóng, vẫn cần dữ liệu đã được nạp phù hợp.

Trong hệ thống API, lựa chọn thực tế thường là dựng **DTO có trường loại** ngay trong transactional service:

~~~java
public record PaymentView(
        Long id,
        String kind,
        long amountMinor
) {}
~~~

Khi đã xác định `kind` bên trong transaction, controller/serializer không cần đụng tới entity proxy để xử lý loại.

## 6. `equals()`, `hashCode()` và proxy: vì sao dễ sai hơn `instanceof`?

Ứng dụng Java thường dùng `equals` để so sánh “hai giá trị có bằng nhau không”. Với entity Hibernate, cần quyết định **bằng nhau theo object reference, theo database identity hay theo business key**. Không có một mẫu `equals()/hashCode()` đúng cho mọi domain, ID generator và inheritance hierarchy.

### 6.1. Lỗi thứ nhất: so sánh strict Java runtime class

Một cách viết phổ biến:

~~~java
@Override
public boolean equals(Object obj) {
    if (this == obj) return true;
    if (obj == null || getClass() != obj.getClass()) {
        return false;
    }
    Payment other = (Payment) obj;
    return id != null && id.equals(other.id);
}
~~~

Vấn đề khi có proxy:

- `getClass()` trên entity thật trả `CardPayment.class`.
- `getClass()` trên proxy có thể trả lớp proxy runtime.
- Hai tham chiếu cùng persistent identity bị đánh giá **khác kiểu** dù dữ liệu đại diện giống nhau.

Hơn nữa, việc truy cập **field `id` trực tiếp** trên một proxy chưa khởi tạo có thể không phản ánh identifier theo cách mong đợi. Proxy có thể giữ ID trong `LazyInitializer` và sử dụng accessor/interception; đừng viết phép so sánh dựa trên việc đọc trực tiếp private field của proxy.

### 6.2. Lỗi thứ hai: dùng `instanceof` quá rộng

Có người đổi thành:

~~~java
if (!(obj instanceof Payment)) {
    return false;
}
~~~

Cách này nhận cả `CardPayment` và `BankTransferPayment` trong cùng một hierarchy. Điều đó **có thể đúng nếu ID của root luôn duy nhất và equality được định nghĩa là identity của root Payment**; nhưng nếu miền nghiệp vụ đòi hỏi phân biệt subtype, hoặc chiến lược tạo ID khiến các bảng subtype có ID trùng mà không có root identity thống nhất, nó có thể xem hai entity khác loại là bằng nhau.

Cũng phải cẩn thận với subclass **override `equals`** theo quy tắc khác:

~~~text
Payment.equals(CardPayment)       → true
CardPayment.equals(Payment)       → false
~~~

Trạng thái này vi phạm yêu cầu **đối xứng** của hợp đồng `equals`. Nếu subclass thêm field mutable vào phép so sánh nhưng lớp cha chỉ so ID, có thể tạo thêm vấn đề bắc cầu và hash consistency.

**Cần định nghĩa một quy tắc identity thống nhất trên toàn hierarchy, tránh mỗi subclass tự thay đổi nó.**

### 6.3. Lỗi thứ ba: ID sinh sau persist và hash code thay đổi

Ví dụ không nên dùng khi ID là giá trị được sinh sau `persist`:

~~~java
@Override
public int hashCode() {
    return id == null ? 0 : id.hashCode();
}
~~~

Trình tự gây lỗi:

~~~java
Set<Payment> payments = new HashSet<>();

Payment p = new CardPayment(...); // id == null
payments.add(p);                  // Dùng hashCode hiện tại.

entityManager.persist(p);        // DB/Hibernate cấp ID cho p.

// hashCode có thể đã thay đổi → cấu trúc HashSet không còn
// tra cứu p theo bucket ban đầu một cách nhất quán.
boolean present = payments.contains(p);
~~~

`HashSet` yêu cầu hash của phần tử **không đổi trong thời gian nó là phần tử của set**. Nếu hash phụ thuộc ID được cấp sau persist, object có thể bị đặt vào bucket không còn tương ứng. Mẫu này có thể không ném exception nhưng tạo hành vi khó hiểu.

### 6.4. Lỗi thứ tư: so sánh association lazy trong `equals`

Đoạn code dạng Lombok `@Data` hoặc `@EqualsAndHashCode` sinh tự động từ **mọi field** có thể kéo theo:

~~~text
Order.equals(...)
    → so sánh customer
        → khởi tạo customer proxy
            → phát SELECT hoặc LazyInitializationException
    → so sánh orderItems
        → khởi tạo collection
            → truy vấn thêm và có thể đi vào vòng lặp graph
~~~

Nếu association hai chiều được đưa vào `equals/hashCode/toString`, có thể xảy ra recursion, thêm truy vấn hàng loạt hoặc lỗi khi session đã đóng. Với entity JPA, không nên mặc định cho Lombok so sánh toàn bộ field; hãy xác định rõ các field đại diện cho identity.

## 7. Một mẫu equality theo ID cho hierarchy `JOINED` có root identity thống nhất

Với hierarchy `Payment` dùng chung **một root ID duy nhất**, ta có thể chọn định nghĩa:

> Hai `Payment` biểu diễn cùng entity khi chúng thuộc **cùng root hierarchy** và có **cùng ID khác null**. Subtype không phải thành phần của equality vì ID root đã định danh entity duy nhất.

Đây là **lựa chọn domain cụ thể**, phù hợp với `JOINED`/`SINGLE_TABLE` khi ID được cấp thống nhất qua bảng root. Nó không phải công thức áp dụng bất biến cho mọi entity hoặc `TABLE_PER_CLASS`.

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "payments")
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Payment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    protected Payment() {}

    public Long getId() {
        return id;
    }

    @Override
    public final boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof Payment that)) {
            return false;
        }

        Long myId = getId();
        return myId != null && myId.equals(that.getId());
    }

    @Override
    public final int hashCode() {
        return Payment.class.hashCode();
    }
}
~~~

Giải thích:

1. **`this == other`** giúp một object luôn bằng chính nó, kể cả khi ID chưa được cấp.
2. **`instanceof Payment`** nhận các proxy có class kế thừa root `Payment` mà không đòi so strict runtime class.
3. **`getId()`** dùng accessor thay cho trực tiếp đọc field của `that`; hành vi truy cập ID trên proxy có thể phụ thuộc mapping/provider, nhưng cách này tương thích hơn với proxy getter.
4. **`myId != null`** tránh xem hai entity mới tạo, chưa persist, là cùng entity chỉ vì ID đều null.
5. **`hashCode` ổn định** qua giai đoạn trước/sau khi ID được cấp. Hai đối tượng bằng nhau chắc chắn có cùng hash theo contract.
6. **`final equals/hashCode`** ở root tránh subclass tự thay đổi quy tắc equality theo field riêng, làm mất tính đối xứng/bắc cầu trong hierarchy.

**Điều kiện của mẫu:** namespace định danh root phải thống nhất, không có hai entity khác nhau cùng root ID trong phạm vi so sánh, không dùng ID giả/tạm tái sử dụng tùy tiện. `final` trên phương thức có thể ảnh hưởng cách subclass proxy/interceptor hoạt động; cần giữ logic trong những accessor có hợp đồng rõ ràng và hiểu khả năng lazy initialization. Đặc biệt, phương thức `equals` chỉ dựa ID tránh ép Hibernate tải toàn bộ dữ liệu nếu API proxy hỗ trợ lấy ID không khởi tạo trong cấu hình đó; không bảo đảm tuyệt đối mọi provider/setting đều xử lý giống nhau.

### 7.1. Đánh đổi của hash code hằng

Một hash code giống nhau cho mọi `Payment` khiến các phần tử rơi vào cùng bucket trong `HashMap`/`HashSet`, có thể giảm hiệu năng nếu collection rất lớn. Nó là một cách đổi lấy **tính ổn định khi ID chuyển từ null sang giá trị đã sinh**. Nếu ứng dụng giữ hàng trăm nghìn entity trong hash collection, có thể chọn thiết kế khác như so sánh theo immutable business key được cấp khi khởi tạo, hoặc quản lý collection bằng key ID sau khi persist.

### 7.2. Không đặt loại subclass vào hash nếu equals không phân biệt loại

Một lỗi bất đối xứng về hợp đồng hash:

~~~java
// Sai về hợp đồng nếu equals chỉ dựa root ID:
@Override
public int hashCode() {
    return getClass().hashCode();
}
~~~

Nếu `equals` coi proxy và entity cùng root ID là bằng nhau, nhưng `hashCode` phụ thuộc runtime class proxy vs entity thật, hai object bằng nhau có thể có hash khác nhau. Vi phạm hợp đồng Java khiến `HashSet` và `HashMap` trả kết quả không nhất quán.

### 7.3. Khi cần equality theo concrete subclass

Một số domain yêu cầu **mỗi concrete entity type có identity namespace riêng**. Trong trường hợp đó, entity type phải tham gia `equals` và `hashCode` bằng một **cách xác định loại nhất quán**. Không dùng `Object.getClass()` trực tiếp với proxy. Có thể cân nhắc `Hibernate.getClass`, nhưng phương thức này có thể khởi tạo proxy và gây truy vấn/exception khi không còn session.

Nếu equality phải chạy trên entity detached hoặc trong collections xuyên session, nên cân nhắc một **key value object ổn định** chứa đúng loại và ID do ứng dụng tạo ra ở ranh giới transaction, thay vì để `equals` trên entity tự thực thi SQL chỉ để xác định subtype.

Ví dụ:

~~~java
public record EntityKey(String entityKind, Long id) {
    public EntityKey {
        if (entityKind == null || entityKind.isBlank()) {
            throw new IllegalArgumentException("entityKind required");
        }
        if (id == null) {
            throw new IllegalArgumentException("Persisted id required");
        }
    }
}

// Tạo key sau khi biết loại và ID trong transactional service:
EntityKey key = new EntityKey("CARD_PAYMENT", 42L);
~~~

Ở đây `entityKind` là **mã domain ổn định** được thiết kế tường minh, không phải tên lớp proxy `getClass().getName()`. Record Java có value equality ổn định và không cần Session để so sánh.

## 8. So sánh entity trong thực tế: chọn tiêu chí theo ngữ cảnh

| Bài toán | Nên dùng | Tránh |
| --- | --- | --- |
| Kiểm tra hai reference trong **cùng một persistence context** thực sự là cùng object | `==` khi đó chính là mục tiêu kiểm tra reference identity | Suy rộng `==` thành equality xuyên session |
| So sánh hai entity managed/detached đại diện cùng hàng DB | Quy tắc equality theo persistent identity được định nghĩa rõ, hoặc key value object | So trực tiếp tất cả field, association lazy |
| Phân biệt subtype để xử lý nghiệp vụ | Xác định concrete type trong transaction bằng `Hibernate.getClass` hoặc `Hibernate.unproxy` khi cần | `getClass() == Subclass.class` trên proxy |
| Phân biệt entity cùng root khi ID đã đủ duy nhất | Root identity + non-null ID theo mô hình thống nhất | Subclass `equals` khác nhau gây bất đối xứng |
| Phân biệt loại theo ID ở nhiều service/DB | Key gồm namespace/tenant/type/ID theo hợp đồng | Chỉ so numeric ID |
| Làm key lâu dài trong cache/event/DTO | Immutable key đã chuẩn hóa | Giữ entity proxy/detached mutable làm key |
| In log | ID, entity name/domain kind được chuẩn hóa, correlation ID | `toString` duyệt lazy associations |
| Kiểm tra existence | Query/`find` trong transaction, kết hợp ràng buộc DB | Coi `getReference` là câu xác nhận entity tồn tại |

### 8.1. Tenant và persistence-unit identity

Một `Payment(id = 42)` của tenant A không nhất thiết là cùng entity nghiệp vụ với `Payment(id = 42)` của tenant B. Nếu ứng dụng multi-tenant cho phép so sánh entity/DTO ở ngoài một persistence context, key phải chứa **tenant scope** khi ID không duy nhất toàn hệ thống. Tương tự, hai database độc lập có `id = 42` không tạo identity chung.

Trong Hibernate session theo tenant, runtime quản lý identity trong bối cảnh đã cấu hình; **business equality xuyên tenant** phải do ứng dụng định nghĩa, không sao chép logic đơn giản dựa ID sang mọi ngữ cảnh.

## 9. Những trường hợp thường gây `LazyInitializationException`

Một proxy chỉ có thể tải trạng thái khi có đủ ngữ cảnh Hibernate phù hợp. Ví dụ:

~~~java
Payment reference;
try (Session session = sessionFactory.openSession()) {
    reference = session.getReference(Payment.class, 42L);
} // Session đã đóng.

Class<?> type = Hibernate.getClass(reference); // Có thể cần initialize.
~~~

Nếu proxy chưa được khởi tạo, đoạn cuối có thể ném `LazyInitializationException`. Ngoài `Hibernate.getClass`, các thao tác sau cũng có thể gây vấn đề nếu cần truy vấn:

- `Hibernate.unproxy(reference)`.
- Gọi getter của field chưa được tải.
- Gọi method domain yêu cầu trạng thái của subclass.
- `equals`/`hashCode`/`toString` nếu chúng duyệt association hoặc cần class thực.

Một phản ứng thường gặp là kéo dài Session tới tận controller/view để “hết lỗi lazy”. Cách ấy có thể tạo SQL ẩn trong tầng presentation và N+1. Thay vào đó, xác định **dữ liệu và subtype cần thiết trong transaction**, rồi chuyển thành DTO.

~~~mermaid
sequenceDiagram
    participant UI as Controller
    participant S as Transactional service
    participant H as Hibernate Session
    participant DB as Database
    UI->>S: Lấy PaymentView(id)
    S->>H: find/load Payment theo ID
    H->>DB: SQL để xác định entity/subtype
    DB-->>H: Payment và subtype
    S->>H: unproxy/xác định loại nếu cần
    S-->>UI: PaymentView(id, kind, amount)
    Note over UI: Không cần proxy sau khi service trả về
~~~

### 9.1. Không coi eager fetch là biện pháp sửa mọi lỗi subtype

Đổi mọi association từ `LAZY` sang `EAGER` có thể giúp một code path nhận được entity đã tải, nhưng thường làm số SQL và dữ liệu nạp tăng, vẫn không bảo đảm các trường hợp proxy khác như `getReference`. Cần chọn fetch plan phù hợp theo ca sử dụng: entity graph, fetch join, truy vấn projection hoặc explicit load trong transaction.

### 9.2. Xử lý `EntityNotFoundException` đúng bản chất

Một `getReference(Payment.class, missingId)` có thể tạo proxy dù bản ghi không tồn tại. Khi initialize để tìm subtype, Hibernate mới phát hiện không có hàng và ném exception. Không trả “lớp loại không hỗ trợ” cho dữ liệu ID không tồn tại; hãy phân biệt:

- **Không tồn tại entity**: xử lý 404/loại lỗi nghiệp vụ phù hợp.
- **Entity tồn tại nhưng subtype không đúng yêu cầu**: xử lý 400/409/loại phản hồi theo hợp đồng.
- **Dữ liệu kế thừa không nhất quán giữa các bảng**: lỗi integrity cần điều tra, không chỉ ép kiểu lại.

## 10. Tình huống so sánh kiểu thực thể sai thường gặp

### 10.1. Service nhận root proxy nhưng kiểm tra `instanceof` ngay

~~~java
public boolean canRefund(Payment payment) {
    return payment instanceof CardPayment;
}
~~~

Nếu `payment` là proxy kiểu `Payment`, method có thể trả `false` cho một thanh toán thẻ thật. Hướng xử lý: xác định loại trong transaction rồi dùng chính sách domain, hoặc xây dựng một `PaymentView` có `kind`/`refundable` được tính ở service. Không “sửa” bằng cách cast trực tiếp `(CardPayment) payment` vì proxy có thể không kế thừa CardPayment.

### 10.2. Dùng `getClass()` để định tuyến handler

~~~java
Map<Class<?>, PaymentHandler> handlers = ...;
PaymentHandler handler = handlers.get(payment.getClass());
~~~

Nếu key đăng ký là `CardPayment.class` nhưng runtime object là proxy class, `handlers.get(...)` trả `null`. Nên xác định loại entity bằng API Hibernate khi có session, hoặc key theo mã business type đã chuẩn hóa. Đừng đăng ký handler theo tên lớp proxy sinh tự động.

### 10.3. Dùng Lombok `@Data` trên entity kế thừa

`@Data` có thể sinh `equals`/`hashCode` và `toString` theo field; với JPA entity có association lazy và inheritance, nguy cơ gồm vòng lặp, SQL phụ và equality phụ thuộc trạng thái mutable. Nên chủ động thiết kế các method này; nếu dùng Lombok, giới hạn rõ những field tham gia theo identity contract và tránh association/lazy data.

### 10.4. So entity trước và sau `persist` bằng `HashSet`

Khi ID do DB sinh, entity mới tạo chưa có ID; sau `persist`, ID đổi. Hash dựa ID có thể làm mất khả năng tìm phần tử trong set. Giải pháp có thể là hash ổn định theo lớp gốc/strategy, hoặc đặt entity vào collection sau khi có ID, hoặc dùng business key bất biến nếu domain có.

### 10.5. Test chỉ chạy với initialized entity

Một unit test gọi `em.find(CardPayment.class, id)` rồi thấy `getClass() == CardPayment.class`, sau đó kết luận cách so sánh class an toàn. Nhưng production code lấy association `getReference(Payment.class, id)` có thể tạo proxy. Cần thử cả đường dữ liệu đã tải lẫn proxy chưa khởi tạo, session đang mở và đã đóng để hiểu ranh giới API; nội dung test tùy dự án và giai đoạn kiểm thử.

## 11. Kiểm tra đúng trong service: một ví dụ hoàn chỉnh

Giả sử API trả chi tiết thanh toán thẻ. Yêu cầu là:

1. Payment ID phải tồn tại.
2. Payment ID đó phải là `CardPayment`.
3. Chỉ lấy dữ liệu cần thiết trong transaction.
4. Controller nhận DTO, không giữ proxy.

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.hibernate.Hibernate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentQueryService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional(readOnly = true)
    public CardPaymentView getCardPayment(long id) {
        Payment payment = entityManager.find(Payment.class, id);

        if (payment == null) {
            throw new PaymentNotFoundException(id);
        }

        Payment actual = (Payment) Hibernate.unproxy(payment);

        if (!(actual instanceof CardPayment card)) {
            throw new WrongPaymentTypeException(id);
        }

        return new CardPaymentView(
                card.getId(),
                card.getCardLast4(),
                card.getAmountMinor()
        );
    }
}

public record CardPaymentView(
        Long id,
        String cardLast4,
        long amountMinor
) {}
~~~

`PaymentNotFoundException` và `WrongPaymentTypeException` là exception domain giả định. Ví dụ cũng giả định entity có getter tương ứng. Spring quản lý transaction và proxy `EntityManager` theo cấu hình tích hợp JPA thông thường. `readOnly = true` là hint cho transaction manager/provider, không thay thế permission check hoặc đảm bảo database tuyệt đối không cho ghi.

Nếu ứng dụng đã biết chắc loại và chỉ chấp nhận `CardPayment`, có thể truy vấn **trực tiếp subtype**:

~~~java
CardPayment card =
        entityManager.find(CardPayment.class, id);

if (card == null) {
    // Không có CardPayment ID này theo mapping đang dùng.
}
~~~

Đây thường là cách rõ nghĩa hơn khi requirement là “tìm thanh toán thẻ”, nhưng cần nhớ: nếu root ID tồn tại ở subtype khác, `find(CardPayment.class, id)` có thể trả `null`. Muốn phân biệt “không có Payment” với “có Payment nhưng khác loại”, vẫn phải kiểm tra root nếu hợp đồng API yêu cầu hai lỗi khác nhau.

### 11.1. Vì sao phương thức trả DTO?

Sau khi transaction kết thúc, `CardPaymentView` chứa giá trị đơn giản không phụ thuộc session. Controller có thể serialize, so sánh, chuyển qua thread hoặc gửi message mà không vô tình kích hoạt SQL. Nếu cần biết entity type, view có thể mang một mã loại `"CARD"` được định nghĩa từ domain thay vì mang `Class<?>` runtime.

### 11.2. Đừng dựa vào `toString()` và log để “xác nhận class”

Một số IDE, debugger hoặc logger tự gọi getter/`toString` để hiển thị object. Điều này có thể vô tình initialize proxy. Vì vậy hành vi “khi debug thấy đúng subtype, lúc chạy thường lại sai” không hiếm. Quan sát qua SQL logger và trạng thái proxy rõ ràng, không dựa vào cách debugger render entity.

## 12. Proxy, bytecode enhancement và hạn chế thiết kế lớp

Hibernate thường cần tạo proxy subclass cho lazy entity. Vì vậy các yếu tố Java sau có thể ảnh hưởng proxy-based lazy loading:

- Class entity **`final`** không thể được subclass theo cơ chế proxy kế thừa lớp.
- Method `final` có thể không được intercept bởi subclass proxy như method có thể override.
- Entity nên có constructor không tham số với mức truy cập phù hợp JPA/Hibernate.
- Các entity không mở rộng được bằng proxy có thể cần cơ chế khác, hoặc dẫn tới hành vi fetch khác.
- Hibernate bytecode enhancement cung cấp một số cơ chế lazy loading thông qua interception trên class đã được tăng cường, không phải lúc nào cũng dùng object proxy subclass giống nhau.

Không nên suy ra rằng “mọi entity là proxy subclass” hoặc “mọi lazy association bắt buộc hoạt động cùng cách”. Các ví dụ trong bài chủ yếu minh họa **cơ chế runtime proxy subclass** phổ biến và rủi ro equality/type check khi gặp cơ chế đó.

**Entity equality nên là một hợp đồng nghiệp vụ rõ ràng, không phụ thuộc vào việc một mapping cụ thể hôm nay có dùng proxy subclass hay không.**

## 13. Lưu ý riêng khi dùng `JOINED`, `SINGLE_TABLE` và `TABLE_PER_CLASS`

### 13.1. `JOINED`

Các subclass chia sẻ primary key của root. Một `Payment(id=42)` có thể thực sự là `CardPayment` dù tham chiếu ban đầu là root proxy. Để xác định subtype, Hibernate có thể phải tra bảng con/discriminator. Logic so sánh root ID có thể phù hợp vì ID root định danh entity trong hierarchy; kiểm tra subtype dựa `instanceof` trên root proxy không đáng tin.

### 13.2. `SINGLE_TABLE`

Subtypes nằm trong một bảng và thường có discriminator. Dữ liệu discriminator giúp Hibernate biết subclass khi hàng đã được đọc, nhưng `getReference(Payment.class, id)` có thể chưa đọc hàng đó. Vì vậy vẫn có cùng nguy cơ khi so strict Java class hoặc `instanceof` ngay trên proxy root.

### 13.3. `TABLE_PER_CLASS`

Mỗi concrete entity có bảng riêng, và HQL root polymorphic có thể dùng nhiều nguồn/`UNION` tùy dialect. ID generation phải bảo đảm danh tính phù hợp với hierarchy. Không lấy một quy tắc equals “root ID duy nhất” từ `JOINED` áp dụng thẳng nếu thiết kế ID của các bảng có thể trùng; equality contract phải tính đến entity type/namespace khi cần.

### 13.4. Kế thừa nhiều cấp

~~~text
Payment
  └── OnlinePayment
        └── CardPayment
~~~

Một `getReference(OnlinePayment.class, id)` có thể tạo proxy có lớp base `OnlinePayment` trong khi entity thực là `CardPayment`. `instanceof OnlinePayment` có thể đúng nhưng `instanceof CardPayment` chưa chắc đúng. Phải hiểu **đối tượng proxy được yêu cầu theo lớp nào**, không dựa vào việc ID có hàng subtype sâu hơn để suy luận kết quả Java `instanceof`.

## 14. Tham khảo và quy tắc áp dụng

- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html): phần fetching, proxies, entity identity và inheritance trong Hibernate ORM.
- [Hibernate ORM `Hibernate` API](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/Hibernate.html): `getClass`, `unproxy`, `isInitialized` và `initialize`.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): `EntityManager.getReference`, `find`, entity identity, persistence context và inheritance mapping.
- [Hibernate ORM Documentation](https://hibernate.org/orm/documentation/): chọn đúng user guide/migration guide khi nâng cấp từ Hibernate 5 lên 6 hoặc thay đổi bytecode enhancement.

Khi làm việc với entity kế thừa, **đừng đánh đồng “lớp của object đang giữ” với “loại entity được database lưu”**. `Object.getClass()` và `instanceof` chỉ biết cấu trúc Java runtime; proxy có thể là lớp đại diện cho gốc hierarchy. Nếu cần subtype thực sự, hãy xác định trong một transaction bằng API Hibernate phù hợp hoặc query trực tiếp subtype; nếu chỉ cần nhận diện entity, hãy chọn quy tắc identity ổn định theo root/type/ID/tenant. Điều này giúp equality giữ đúng hợp đồng Java, đồng thời tránh truy vấn ẩn và lỗi lazy loading ở những nơi chỉ nên làm việc với giá trị thuần.

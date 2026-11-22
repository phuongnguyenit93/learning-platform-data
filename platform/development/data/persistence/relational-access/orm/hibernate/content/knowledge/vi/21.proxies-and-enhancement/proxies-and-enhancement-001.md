# Proxy biểu diễn tham chiếu chưa được khởi tạo

## 1. Một tham chiếu entity không có nghĩa dữ liệu entity đã được tải

Trong Hibernate, một thuộc tính quan hệ có thể trỏ tới một **proxy** đại diện cho entity mà dữ liệu của nó chưa được đọc từ database. Proxy giữ đủ thông tin để nhận diện đối tượng, thường là identifier, và biết cách yêu cầu Hibernate tải trạng thái thật khi ứng dụng cần truy cập dữ liệu.

Giả sử một bài viết tham chiếu tới tác giả:

```text
Database
  articles
    id=42, title="Lazy loading", author_id=7
  authors
    id=7, name="Lan", biography="..."

Khi tải Article #42:
  Article #42 [MANAGED]
      ├── title = "Lazy loading"       đã tải
      └── author = Author proxy #7     chưa tải trạng thái
                  ├── id = 7           đã biết
                  └── name             chưa tải

Khi code cần author.getName():
  Proxy yêu cầu Session tải Author #7
                  │
                  ▼
             SELECT authors ...
                  │
                  ▼
           Proxy được khởi tạo
```

Điểm cốt lõi: một association có thể được biểu diễn bằng reference trước khi Hibernate đọc toàn bộ hàng liên quan. Nhờ vậy, query lấy Article không nhất thiết phải join và materialize tất cả Author, Category, Publisher hoặc những quan hệ khác.

Proxy không phải một bản sao dữ liệu đầy đủ, cũng không phải một entity khác có identity riêng. Nó là đại diện lazy cho entity mục tiêu, gắn với cơ chế quản lý của Hibernate. Khi được khởi tạo, proxy cung cấp trạng thái của entity mà nó đại diện.

## 2. Proxy giải quyết vấn đề gì?

Một ứng dụng có thể tải hàng nghìn Order để hiển thị mã đơn và ngày tạo. Mỗi Order tham chiếu Customer, Address, Payments và OrderLines. Nếu mọi quan hệ đều được tải ngay, một màn hình chỉ cần hai cột có thể kéo theo rất nhiều SQL, object Java và dữ liệu không sử dụng.

Lazy proxy cho phép Hibernate trì hoãn việc tải một entity liên quan tới thời điểm ứng dụng thực sự cần trạng thái của nó.

```java
Order order = em.find(Order.class, 100L);

System.out.println(order.getId());
System.out.println(order.getOrderNumber());

// Chỉ khi cần thông tin khách hàng:
String customerName = order.getCustomer().getName();
```

Nếu `Order.customer` được ánh xạ lazy và proxy chưa khởi tạo, Hibernate có thể chỉ tải hàng Order trước. Lệnh gọi `getName()` mới kích hoạt SELECT cho Customer.

Lợi ích:

- Tránh tải dữ liệu quan hệ không cần dùng.
- Giảm lượng dữ liệu truyền từ database khi query ban đầu.
- Giảm số entity được materialize trong persistence context.
- Cho phép mô hình object có quan hệ phong phú mà không buộc mọi association đều eager.

Nhưng lazy loading không có nghĩa tự động nhanh hơn. Nếu ứng dụng truy cập một association cho từng hàng trong danh sách, nó có thể tạo N+1 queries. Muốn dùng proxy hiệu quả, cần thiết kế fetch plan phù hợp với từng use case.

## 3. Proxy entity và collection wrapper là hai cơ chế khác nhau

Hibernate dùng nhiều dạng đại diện lazy:

| Thành phần | Ví dụ | Đại diện cho | Khi nào tải? |
|---|---|---|---|
| Entity proxy | `Order.customer` | Một entity có identifier cụ thể | Khi truy cập state cần tải của entity |
| Persistent collection | `Order.lines` | Tập hợp các phần tử quan hệ | Khi thao tác cần nội dung collection |
| Enhanced lazy attribute | Một thuộc tính entity được bytecode enhancement hỗ trợ | Trạng thái thuộc tính cụ thể | Khi thuộc tính lazy được truy cập |

Ví dụ:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines = new ArrayList<>();
```

`customer` thường được biểu diễn bằng entity proxy. `lines` thường được biểu diễn bằng persistent collection wrapper của Hibernate. Collection wrapper có thể giữ trạng thái “chưa khởi tạo” và biết cách tải các phần tử khi ứng dụng duyệt hoặc gọi thao tác cần nội dung.

Vì vậy, khi nói “proxy” trong bài này, trọng tâm là **proxy đại diện cho một entity tham chiếu chưa khởi tạo**. Đừng gọi mọi collection wrapper là entity proxy; cách Hibernate theo dõi và khởi tạo chúng có liên quan nhưng không hoàn toàn giống nhau.

## 4. Proxy thường giữ những gì?

Một proxy entity thường có:

- **Identifier:** khóa định danh của entity đích, đủ để biết proxy đại diện cho hàng nào.
- **Thông tin khởi tạo:** cơ chế nội bộ để tải entity thật khi cần.
- **Liên kết tới Session/Persistence Context:** khi còn gắn với session mở, proxy có thể yêu cầu Hibernate truy vấn database.
- **Trạng thái initialized/uninitialized:** cho biết dữ liệu entity đã được tải hay chưa.

```text
Customer proxy
  identifier = 7
  initialized = false
  session = Session A
  lazy initializer
       │
       ├── getIdentifier() → 7
       │
       └── cần getName()
                │
                ▼
          Session A.load(7)
                │
                ▼
          Database SELECT
                │
                ▼
          initialized = true
          name = "Lan"
```

Đây là mô hình giải thích, không phải cấu trúc class công khai mà ứng dụng nên tự tạo. Chi tiết proxy và initializer là nội bộ Hibernate, có thể thay đổi theo phiên bản.

## 5. Tạo proxy bằng EntityManager.getReference()

Jakarta Persistence cung cấp:

```java
Customer customer = em.getReference(Customer.class, 7L);
```

Trong Hibernate, nếu entity chưa có trong persistence context và mapping cho phép proxy, lời gọi này thường trả về một proxy đại diện cho Customer #7 mà chưa cần đọc toàn bộ trạng thái Customer ngay lập tức.

So sánh:

```java
Customer loaded = em.find(Customer.class, 7L);
Customer reference = em.getReference(Customer.class, 7L);
```

| API | Mục đích | Hành vi thường gặp |
|---|---|---|
| `em.find(Customer.class, id)` | Tìm và lấy entity state | SELECT để đọc entity nếu chưa có trong PC/cache phù hợp |
| `em.getReference(Customer.class, id)` | Lấy reference tới entity theo ID | Có thể trả proxy chưa khởi tạo, trì hoãn SELECT |

JPA định nghĩa `getReference()` là cách lấy reference; provider có thể trì hoãn việc kiểm tra entity có tồn tại tới lúc trạng thái được truy cập. Hành vi SQL chính xác phụ thuộc provider và trạng thái persistence context. Không coi việc gọi `getReference()` là bằng chứng rằng hàng đó chắc chắn tồn tại.

### 5.1. Dùng getReference để thiết lập association

Một tình huống phổ biến là tạo OrderLine và biết Order ID từ command:

```java
@Transactional
public void addLine(Long orderId, String sku, int quantity) {
    Order order = em.getReference(Order.class, orderId);
    OrderLine line = new OrderLine(order, sku, quantity);
    em.persist(line);
}
```

Nếu constructor chỉ gán reference và code không đọc state của Order, Hibernate có thể dùng identifier của proxy để ghi FK mà không tải toàn bộ Order. Điều này hữu ích khi chỉ cần tham chiếu tới entity đã biết ID.

Tuy nhiên:

- Nếu ID không tồn tại, lỗi có thể xuất hiện khi proxy được khởi tạo hoặc khi database kiểm tra FK lúc flush/commit.
- Nếu domain phải xác nhận Order tồn tại, còn ở trạng thái DRAFT và thuộc đúng user, chỉ lấy reference là chưa đủ; phải query/load state cần kiểm tra.
- Nếu persistence context đã có Order managed, `getReference()` có thể trả lại instance đã có thay vì tạo proxy mới.
- Nếu association có cascade hoặc mapping đặc biệt, SQL và việc tải dữ liệu có thể khác ví dụ đơn giản.

### 5.2. Không dùng getReference để bỏ qua kiểm tra nghiệp vụ

Proxy chỉ cung cấp reference theo ID; nó không chứng minh mọi invariant đều đúng. Nếu nghiệp vụ yêu cầu Customer đang hoạt động, có quyền mua hàng và thuộc đúng tenant hiện tại, code phải kiểm tra những điều kiện đó bằng dữ liệu phù hợp trong transaction.

## 6. Khởi tạo proxy: khi nào SELECT được thực hiện?

Proxy được khởi tạo khi ứng dụng truy cập dữ liệu cần trạng thái thật của entity. Ví dụ:

```java
Customer customer = em.getReference(Customer.class, 7L);

// Đọc identifier thường không cần khởi tạo proxy trong Hibernate:
Long customerId = customer.getId();

// Truy cập thuộc tính cần trạng thái:
String name = customer.getName();
```

Trong Hibernate, đọc identifier qua getter tương ứng thường không cần khởi tạo proxy vì identifier đã nằm trong proxy. Nhưng đây là chi tiết cần kiểm chứng với mapping/access strategy và phiên bản cụ thể; không xây logic correctness dựa vào giả định mọi getter ID đều luôn miễn phí.

Khi gọi getter cho field khác, Hibernate cần trạng thái Customer. Nếu proxy còn gắn với Session đang mở, nó tải hàng tương ứng và chuyển sang initialized.

### 6.1. Một proxy có thể được khởi tạo bởi nhiều cách

Không chỉ getter mới có thể kích hoạt tải:

- Gọi method nghiệp vụ trên entity cần truy cập field chưa tải.
- Truy cập một thuộc tính lazy khác.
- Duyệt association lồng bên trong proxy sau khi proxy đã khởi tạo.
- Gọi API Hibernate yêu cầu lấy entity thật/unproxy.
- Serializer, debugger hoặc logging gọi getter/`toString()` một cách vô tình.

Một câu log đơn giản có thể tạo SQL nếu `toString()` đọc field lazy. Hãy giới hạn nội dung log ở các field scalar an toàn.

### 6.2. Kiểm tra trạng thái proxy

Hibernate cung cấp utility:

```java
import org.hibernate.Hibernate;

Customer customer = em.getReference(Customer.class, 7L);

boolean initializedBefore = Hibernate.isInitialized(customer);

String name = customer.getName();

boolean initializedAfter = Hibernate.isInitialized(customer);
```

Nếu proxy ban đầu chưa được khởi tạo và thao tác getter thành công trong session, giá trị sau thường là true.

Đối với ứng dụng ưu tiên Jakarta Persistence, có thể kiểm tra trạng thái load qua:

```java
PersistenceUnitUtil util =
        em.getEntityManagerFactory().getPersistenceUnitUtil();

boolean loaded = util.isLoaded(customer);
boolean nameLoaded = util.isLoaded(customer, "name");
```

Các API này dùng để quan sát trạng thái load, không nên biến thành điều kiện nghiệp vụ kiểu “nếu chưa loaded thì coi như khách hàng không tồn tại”.

## 7. Proxy và persistence context identity

Trong một persistence context, Hibernate duy trì identity cho entity theo loại và identifier. Khi đã có một managed instance cho Customer #7, một lần tải/reference tiếp theo thường sử dụng cùng managed instance tương ứng:

```java
Customer first = em.getReference(Customer.class, 7L);
Customer second = em.find(Customer.class, 7L);

// Cùng persistence context có thể trả cùng managed reference.
System.out.println(first == second);
```

Kết quả cụ thể phụ thuộc thứ tự tải, trạng thái PC và cách proxy được khởi tạo, nhưng nguyên tắc identity map vẫn quan trọng: không tạo nhiều bản managed độc lập cho cùng một entity identity trong cùng PC.

Proxy không phải một entity thứ hai trong database. Nó là cách Hibernate hiện thực reference lazy trong memory. Khi được khởi tạo, nó đại diện cho cùng entity ID, không tạo ra một row mới.

## 8. LazyInitializationException và ranh giới Session

Hibernate thường ném `LazyInitializationException` khi ứng dụng cố khởi tạo proxy/collection lazy mà không có Session đang mở phù hợp.

```java
Order order;

try (Session session = sessionFactory.openSession()) {
    order = session.get(Order.class, 100L);
}

// Session đóng trước khi truy cập Customer proxy.
String customerName = order.getCustomer().getName();
```

Lỗi không có nghĩa Order không tồn tại. Order đã được tải, nhưng proxy Customer chưa có trạng thái và không còn Session để tải nó.

### 8.1. Giải pháp đúng: tải dữ liệu trong transaction/service boundary

Nếu use case cần tên khách hàng, hãy query/fetch đúng dữ liệu khi transaction còn mở:

```java
@Transactional(readOnly = true)
public OrderSummary getOrder(Long id) {
    Order order = em.createQuery(
            "select o from Order o " +
            "join fetch o.customer " +
            "where o.id = :id",
            Order.class)
            .setParameter("id", id)
            .getSingleResult();

    return new OrderSummary(
            order.getId(),
            order.getOrderNumber(),
            order.getCustomer().getName());
}
```

Ví dụ giả định `OrderSummary` là DTO phù hợp và transaction interceptor hoạt động. Query join fetch tải Customer cùng Order để method lấy đủ dữ liệu trước khi persistence context kết thúc.

Một lựa chọn khác là constructor projection:

```java
public record OrderSummary(
        Long id, String orderNumber, String customerName) {}
```

```java
List<OrderSummary> rows = em.createQuery(
        "select new com.example.read.OrderSummary(" +
        "  o.id, o.orderNumber, c.name" +
        ") from Order o join o.customer c " +
        "where o.id = :id",
        OrderSummary.class)
        .setParameter("id", id)
        .getResultList();
```

DTO projection không giữ proxy entity trong response và thường là lựa chọn rõ ràng cho API read model.

### 8.2. Không mở Session toàn thời gian chỉ để che lỗi

Open Session in View giữ persistence context mở tới tầng web/view, nên một số lazy access ngoài service có thể chạy được. Nhưng nó có thể che khuất N+1 queries, khiến serializer tự phát SQL và làm database access rải rác ngoài transaction nghiệp vụ.

Hãy ưu tiên xác định dữ liệu cần dùng và tải nó ở service/query boundary. Dùng Open Session in View chỉ khi kiến trúc chủ động chấp nhận semantics và chi phí của nó.

## 9. Proxy khác với việc gọi find()

`find()` thường được dùng khi ứng dụng cần entity state ngay:

```java
Customer customer = em.find(Customer.class, customerId);
String name = customer.getName();
```

`getReference()` thường dùng khi chỉ cần một reference theo ID:

```java
Customer customer = em.getReference(Customer.class, customerId);
order.setCustomer(customer);
```

| Nhu cầu | API thường phù hợp |
|---|---|
| Hiển thị tên/email/field của Customer | `find()` hoặc query projection |
| Kiểm tra trạng thái/tenant/quyền của Customer | Tải state cần thiết bằng query phù hợp |
| Gán FK tới Customer đã biết ID và không cần đọc field | `getReference()` |
| Chỉ muốn truyền identifier qua tầng API | Dùng ID trong command/DTO, không cần proxy |
| Cần chắc chắn entity tồn tại ngay và xử lý not-found | `find()` và kiểm tra null |
| Muốn trì hoãn việc kiểm tra existence tới lúc cần state | `getReference()` theo semantics provider |

### 9.1. Entity không tồn tại

Với:

```java
Customer customer = em.getReference(Customer.class, 999999L);
```

Hibernate có thể trả proxy trước mà chưa SELECT. Khi code truy cập field cần tải, provider có thể ném `EntityNotFoundException` nếu không tìm thấy row. Nếu code chỉ gán proxy vào association rồi flush, FK constraint của database có thể phát hiện reference không tồn tại.

Do đó, nếu nghiệp vụ cần phản hồi not-found ở đầu request, đừng chỉ tạo proxy và cho rằng đã xác nhận dữ liệu. Dùng `find()` hoặc query kiểm tra rõ ràng.

## 10. Proxy trong các association JPA

### 10.1. @ManyToOne

JPA mặc định `@ManyToOne` là EAGER. Để trì hoãn tải, khai báo:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;
```

Trong Hibernate, quan hệ này thường phù hợp với entity proxy: hàng Order có FK `customer_id`; Hibernate biết ID Customer và có thể tạo proxy thay vì tải Customer ngay.

Đây là lý do cần khai báo LAZY tường minh cho nhiều to-one associations nếu use case không luôn cần dữ liệu liên quan. Tuy nhiên, `FetchType.LAZY` trong JPA là hint; provider có thể có giới hạn và hành vi phụ thuộc mapping.

### 10.2. @OneToOne

One-to-one lazy phức tạp hơn, nhất là khi FK nằm ở phía inverse hoặc quan hệ optional. Hibernate có thể cần biết association có tồn tại hay không để quyết định trả null hay proxy; một số trường hợp cần bytecode enhancement để lazy loading hoạt động như mong muốn.

```java
@OneToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "profile_id")
private Profile profile;
```

Không giả định mọi `@OneToOne(fetch=LAZY)` đều tạo proxy và không phát SQL ở thời điểm load owner. Hãy kiểm tra SQL trên phiên bản Hibernate và mapping thực tế.

### 10.3. @OneToMany và @ManyToMany

Các quan hệ collection thường được biểu diễn bằng persistent collection wrapper, không phải một entity proxy duy nhất:

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines = new ArrayList<>();

@ManyToMany(fetch = FetchType.LAZY)
private Set<Tag> tags = new HashSet<>();
```

Khi gọi `order.getLines().size()` hoặc duyệt collection, Hibernate có thể tải các phần tử. Mỗi OrderLine có thể tiếp tục chứa proxy tới Product hoặc Order. Như vậy, một graph có thể kết hợp collection wrapper và nhiều entity proxy.

### 10.4. @ElementCollection

Với collection các giá trị như tag text hoặc phone numbers:

```java
@ElementCollection(fetch = FetchType.LAZY)
@CollectionTable(
        name = "account_phone_numbers",
        joinColumns = @JoinColumn(name = "account_id"))
@Column(name = "phone_number")
private Set<String> phoneNumbers = new HashSet<>();
```

Hibernate quản lý collection wrapper để tải các giá trị từ collection table. Phần tử String không phải entity proxy và không có identity riêng.

## 11. Proxy và bytecode enhancement

Proxy entity là một cách Hibernate triển khai lazy reference, thường dựa trên subclass/proxy mechanism. Hibernate cũng hỗ trợ **bytecode enhancement** để thêm logic lazy loading/interception vào entity class.

Hai cơ chế có liên hệ nhưng không đồng nhất:

| Proxy-based lazy loading | Bytecode-enhanced lazy loading |
|---|---|
| Đại diện entity bằng proxy object | Thêm interception vào entity bytecode |
| Thường tạo subclass proxy cho entity reference | Có thể trì hoãn tải từng thuộc tính/nhóm thuộc tính |
| Có giới hạn liên quan class/method có thể override | Cần enhancement được cấu hình và chạy đúng |
| Phù hợp cho nhiều to-one references | Hỗ trợ lazy attribute loading và một số mapping khó hơn |

```text
Proxy-based:
  Order.customer → CustomerProxy(id=7)
  gọi getName() → initialize Customer

Enhanced attribute loading:
  Document được tạo instance có interceptor
  document.getLargeBody()
      → interceptor tải thuộc tính body khi cần
```

Bytecode enhancement không tự biến mọi field thành lazy; phải khai báo mapping/fetch group phù hợp và bật enhancement theo build/runtime hướng dẫn của Hibernate version đang dùng.

### 11.1. Không cần enhancement để hiểu mọi proxy

Những ví dụ `getReference()` và `@ManyToOne(fetch=LAZY)` trong bài mô tả proxy entity theo cách phổ biến. Khi dùng enhancement, một số chi tiết class/reference có thể khác. Code nghiệp vụ nên dựa vào API JPA/Hibernate được hỗ trợ như `Hibernate.isInitialized()`, `Hibernate.initialize()` hoặc persistence utility thay vì cast và thao tác trực tiếp vào class proxy nội bộ.

## 12. Giới hạn proxy và các class entity

Proxy subclass phải có khả năng kế thừa và intercept các method phù hợp. Vì vậy, một số cấu trúc Java có thể gây hạn chế:

- Entity class `final` không thể được subclass proxy theo cách thông thường.
- Method `final` không thể bị override/intercept bởi subclass proxy.
- Constructor và access strategy phải tương thích với yêu cầu entity của JPA/Hibernate.
- Các method không mở cho proxy interception có thể khiến lazy behavior không hoạt động như kỳ vọng.

Ví dụ:

```java
public final class Customer {
    // Một entity final có thể gây trở ngại cho subclass proxy.
}
```

Hoặc:

```java
public class Customer {
    public final String getName() {
        return name;
    }
}
```

Method final có thể ngăn proxy override getter để kích hoạt initialization. Chi tiết chính xác còn phụ thuộc enhancement, access strategy và Hibernate version; khi thiết kế entity cần tuân theo yêu cầu proxy/enhancement của provider.

### 12.1. Không dùng class proxy như một loại nghiệp vụ

Một proxy có thể là subclass do Hibernate tạo. Vì thế, `customer.getClass() == Customer.class` có thể trả false dù object đại diện cho Customer. Không dùng kiểm tra class equality trực tiếp như cách xác định loại entity khi có proxy.

Hibernate có API:

```java
Class<?> entityType = Hibernate.getClass(customer);
```

API này trả class entity thực tế; tùy proxy và mapping, việc xác định có thể khởi tạo proxy. Không gọi nó trong vòng lặp lớn nếu không hiểu SQL/initialization cost.

## 13. Proxy và equals()/hashCode()

Entity proxy làm cho việc so sánh object phức tạp hơn. Một method `equals()` được viết thiếu cẩn thận có thể:

- Gọi getter lazy và vô tình khởi tạo proxy.
- So sánh `getClass()` rồi coi proxy và entity class là hai loại khác nhau.
- Dùng generated ID chưa có ở transient entity làm hash code thay đổi sau persist.
- Truy cập association trong `equals()/hashCode()`, gây N+1 hoặc LazyInitializationException.

Ví dụ không tốt:

```java
@Override
public boolean equals(Object other) {
    if (other == null || getClass() != other.getClass()) {
        return false;
    }
    Customer that = (Customer) other;
    return Objects.equals(this.getId(), that.getId())
            && Objects.equals(
                    this.getCompany().getName(),
                    that.getCompany().getName());
}
```

Code này có thể gặp cả vấn đề proxy class và lazy association. Một quy tắc thực dụng:

- Không đưa association lazy vào equals/hashCode.
- Chọn equality strategy nhất quán với lifecycle và identifier của entity.
- Nếu dùng natural key, key phải ổn định và có uniqueness theo domain.
- Nếu dùng generated ID, xử lý đúng transient entity chưa có ID và hash collection sau persist.
- Nếu cần so sánh proxy/entity class, dùng chiến lược tương thích proxy/provider; không áp dụng một đoạn equals chung cho mọi domain mà chưa xác định semantics.

Không có một công thức equals/hashCode duy nhất phù hợp mọi entity. Điều quan trọng là không để equality method vô tình tải graph hoặc phá equality giữa proxy và entity đại diện cùng identity.

### 13.1. toString() cũng cần cẩn thận

Lombok `@Data` hoặc `@ToString` mặc định có thể đưa các association vào chuỗi. Logging một entity có thể truy cập proxy/collection và tạo nhiều SELECT. Với entity JPA, hãy giới hạn `toString()` ở các field scalar an toàn, thường là ID và một số giá trị đơn giản đã có.

## 14. Proxy và quan hệ kế thừa entity

Khi entity dùng `@Inheritance`, proxy có thể đại diện cho một kiểu entity trong hierarchy. Việc xác định subtype cụ thể có thể cần thông tin discriminator hoặc query, đặc biệt khi code muốn biết chính xác runtime class.

```java
@Entity
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "payment_type")
public abstract class Payment {
    @Id
    private Long id;
}

@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {
    private String lastFourDigits;
}
```

Một association khai báo kiểu `Payment` có thể được Hibernate biểu diễn bằng proxy cho đến khi cần xác định/tải subtype state. Không nên dùng `payment.getClass()` để quyết định nghiệp vụ trước khi hiểu proxy và inheritance mapping.

Nếu nghiệp vụ cần dữ liệu subtype, hãy query với fetch plan hoặc JPQL phù hợp, ví dụ dùng `TREAT()` khi cần lọc theo subtype. Không tự ép cast một proxy thành subclass cụ thể khi chưa biết type thực tế.

## 15. Hibernate utility để kiểm soát proxy

### 15.1. Kiểm tra initialized

```java
boolean initialized = Hibernate.isInitialized(customer);
```

Với collection:

```java
boolean linesLoaded = Hibernate.isInitialized(order.getLines());
```

Utility này hữu ích trong code hạ tầng, logging hoặc integration tests. Không nên để logic nghiệp vụ thay đổi kết quả chỉ vì một association tình cờ đã được tải trước đó.

### 15.2. Initialize chủ động

```java
Hibernate.initialize(order.getCustomer());
Hibernate.initialize(order.getLines());
```

Gọi khi Session còn mở. Với collection, initialize thường tải collection state; nó không tự bảo đảm mọi association bên trong từng phần tử cũng được khởi tạo.

```java
Hibernate.initialize(order.getLines());

for (OrderLine line : order.getLines()) {
    // Product trên mỗi line có thể vẫn là proxy.
    Hibernate.initialize(line.getProduct());
}
```

Không initialize đệ quy toàn bộ graph một cách máy móc. Với collection lớn, việc tải toàn bộ có thể gây tốn bộ nhớ và truy vấn. Hãy chọn fetch plan phù hợp.

### 15.3. Unproxy

Hibernate có utility để lấy object không còn là proxy wrapper:

```java
Customer actual = Hibernate.unproxy(customer, Customer.class);
```

Unproxy thường yêu cầu proxy được khởi tạo để lấy entity thực tế. Nếu Session đã đóng và proxy chưa khởi tạo, thao tác này không thể tải state như mong muốn. Dùng unproxy chỉ khi thực sự cần class/instance cụ thể; nhiều code chỉ cần gọi method entity thông thường và không cần biết proxy tồn tại.

### 15.4. Không cast sang HibernateProxy để truy cập nội bộ nếu không cần

Hibernate có type như `org.hibernate.proxy.HibernateProxy` và lazy initializer, nhưng đây là chi tiết provider-specific. Code nghiệp vụ nên dùng JPA API hoặc utility Hibernate được công bố. Truy cập initializer nội bộ làm ứng dụng phụ thuộc mạnh vào implementation và có thể hỏng khi nâng version.

## 16. Proxy và N+1 queries

Proxy trì hoãn tải association, nhưng nếu code truy cập một association cho từng row, nó có thể tạo N+1:

```java
List<Order> orders = em.createQuery(
        "select o from Order o order by o.id",
        Order.class)
        .getResultList();

for (Order order : orders) {
    System.out.println(order.getCustomer().getName());
}
```

Có thể tạo:

1. Một SELECT lấy N Orders.
2. N SELECT riêng để khởi tạo Customer proxy (nếu mỗi order tham chiếu một customer chưa được tải).

Nếu nhiều Order cùng Customer, identity map có thể tránh tải lặp cùng một entity trong cùng PC, nhưng số query vẫn có thể lớn tùy dữ liệu.

### 16.1. Join fetch

Nếu màn hình luôn cần Customer:

```java
List<Order> orders = em.createQuery(
        "select o from Order o " +
        "join fetch o.customer " +
        "order by o.id",
        Order.class)
        .getResultList();
```

Hibernate tải Order và Customer trong một query join (tùy SQL dialect và mapping). Không dùng join fetch nhiều collection lớn một cách tùy tiện; kết quả join có thể nhân số row và tạo duplicate root rows. Một số kết hợp collection fetch với pagination không được hỗ trợ tốt hoặc làm phân trang trong memory.

### 16.2. Entity graph

JPA EntityGraph biểu đạt fetch plan:

```java
EntityGraph<Order> graph = em.createEntityGraph(Order.class);
graph.addAttributeNodes("customer");

Order order = em.find(
        Order.class,
        orderId,
        Map.of("jakarta.persistence.fetchgraph", graph));
```

Fetch graph giúp chỉ định association cần tải cho use case. Chiến lược SQL thực tế phụ thuộc provider; kiểm tra SQL để hiểu số query và lượng dữ liệu.

### 16.3. Batch fetching

Hibernate có thể batch initialize nhiều proxy cùng lúc để giảm N+1. Ví dụ annotation:

```java
import org.hibernate.annotations.BatchSize;

@ManyToOne(fetch = FetchType.LAZY)
@BatchSize(size = 20)
private Customer customer;
```

Hoặc cấu hình default batch fetch size ở SessionFactory. Khi một proxy cần khởi tạo, Hibernate có thể tải thêm các proxy cùng loại đang chờ trong batch bằng một query dùng nhiều ID. Batch fetching giảm số round trips nhưng không thay thế fetch plan; nó không bảo đảm mọi trường hợp đều thành một query duy nhất.

## 17. Proxy, serialization và API boundary

Không nên mặc định serialize entity proxy trực tiếp thành JSON. Proxy có thể:

- Chứa initializer/session reference không phải dữ liệu API.
- Bị serializer gọi getter và kích hoạt lazy loading.
- Tạo vòng tham chiếu trong object graph hai chiều.
- Gây LazyInitializationException sau khi transaction đóng.
- Làm API phụ thuộc cấu trúc entity và mapping ORM.

Thay vào đó, ánh xạ sang DTO trong transaction:

```java
public record CustomerView(Long id, String name) {}
public record OrderView(Long id, String number, CustomerView customer) {}
```

```java
@Transactional(readOnly = true)
public OrderView getOrderView(Long id) {
    Order order = em.createQuery(
            "select o from Order o " +
            "join fetch o.customer where o.id = :id",
            Order.class)
            .setParameter("id", id)
            .getSingleResult();

    Customer customer = order.getCustomer();
    return new OrderView(
            order.getId(),
            order.getOrderNumber(),
            new CustomerView(customer.getId(), customer.getName()));
}
```

DTO chứa dữ liệu cần thiết và không mang theo proxy/session. Nếu cần một danh sách lớn, dùng projection query trực tiếp để tránh materialize entity graph không cần thiết.

## 18. Proxy trong equals, logging và debugger

Những hoạt động tưởng như vô hại có thể khởi tạo proxy:

| Hoạt động | Nguy cơ |
|---|---|
| Gọi getter field không phải ID | SELECT để khởi tạo |
| Gọi `toString()` có association | Tải proxy/collection ngoài dự kiến |
| Gọi `equals()/hashCode()` truy cập quan hệ | N+1 hoặc lỗi ngoài Session |
| JSON serialization | Serializer duyệt graph và gọi getter |
| IDE debugger mở object | Có thể gọi getter tùy cấu hình debugger |
| Logging toàn entity | Có thể khởi tạo proxy và collection |
| Dùng `getClass()` so sánh entity | Nhận class proxy thay vì class entity |

Khi điều tra SQL phát sinh không rõ nguyên nhân, hãy xem stack trace và bật SQL logging có kiểm soát. Một getter bị gọi từ serializer hoặc debugger đôi khi là nguồn query.

## 19. Proxy không thay thế validation và foreign key

Một proxy theo ID không xác nhận mọi điều kiện nghiệp vụ. Ví dụ:

```java
Product product = em.getReference(Product.class, productId);
line.setProduct(product);
em.persist(line);
```

Nếu Product không tồn tại, FK có thể làm flush thất bại. Nếu Product tồn tại nhưng đã ngừng kinh doanh, đã bị xóa mềm hoặc không thuộc tenant, proxy không tự kiểm tra những quy tắc đó.

Hãy phân biệt:

- **Existence:** hàng có tồn tại hay không.
- **Authorization:** người dùng hiện tại có được tham chiếu entity đó không.
- **Business validity:** entity có trạng thái phù hợp với thao tác không.
- **Referential integrity:** database có bảo đảm FK trỏ tới hàng tồn tại không.

Proxy chỉ giải quyết biểu diễn reference lazy; không thay thế những lớp kiểm tra còn lại.

## 20. Một ví dụ đầy đủ: tạo Order mà không tải Customer state

```java
@Entity
@Table(name = "orders")
public class Order {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_number", nullable = false, unique = true)
    private String orderNumber;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected Order() {}

    public Order(String orderNumber, Customer customer) {
        this.orderNumber = orderNumber;
        this.customer = Objects.requireNonNull(customer);
    }

    public Long getId() { return id; }
    public String getOrderNumber() { return orderNumber; }
    public Customer getCustomer() { return customer; }
}
```

Service:

```java
@Transactional
public Long createOrder(String number, Long customerId) {
    Customer customer = em.getReference(Customer.class, customerId);
    Order order = new Order(number, customer);
    em.persist(order);
    return order.getId();
}
```

Trong trường hợp mapping/generator cho phép và không có code nào truy cập field Customer, Hibernate có thể ghi FK `customer_id` mà không SELECT toàn bộ Customer. Tuy nhiên, với generated ID kiểu IDENTITY, Hibernate có thể INSERT sớm để lấy Order ID. Nếu cần kiểm tra Customer còn active, hãy tải trạng thái hoặc thực hiện query điều kiện thay vì chỉ dùng reference.

SQL minh họa có thể chỉ là:

```sql
INSERT INTO orders(order_number, customer_id)
VALUES ('ORD-2026-0042', 7);
```

Nếu khóa ngoại trỏ tới Customer #7 không tồn tại, database từ chối INSERT tại thời điểm thực thi. Nếu FK được defer hoặc mapping có cơ chế khác, thời điểm lỗi có thể khác; transaction phải rollback khi lỗi.

## 21. Khi nào nên dùng proxy reference?

| Tình huống | Cách dùng phù hợp |
|---|---|
| Chỉ cần gán association bằng ID đã biết | `getReference()` có thể tránh SELECT không cần thiết |
| Cần đọc thuộc tính entity đích | Tải bằng `find()` hoặc query có fetch plan |
| Cần kiểm tra trạng thái/authorization | Query state cần thiết trong transaction |
| Cần trả API response | DTO/projection, không trả proxy |
| Cần duyệt collection lớn | Query riêng có phân trang, không initialize toàn collection |
| Cần bảo đảm tồn tại ngay | `find()` và xử lý null |
| Chỉ cần identifier trong command | Truyền ID, tạo reference tại persistence boundary |
| Entity sẽ được dùng sau khi Session đóng | Tải đủ dữ liệu cần thiết và map DTO trước khi rời transaction |

Proxy phù hợp nhất khi application có một reference hợp lệ theo identity nhưng chưa cần state của entity đích.

## 22. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| `LazyInitializationException` khi gọi getter | Proxy chưa khởi tạo và Session đã đóng | Fetch trong service transaction hoặc dùng DTO |
| Gọi `getReference()` nhưng không thấy SELECT | Bình thường nếu proxy chưa cần state | Không coi đó là lỗi; truy cập state khi Session còn mở |
| Proxy tham chiếu ID không tồn tại | Existence được kiểm tra muộn hoặc FK phát hiện lúc flush | Dùng find/query nếu cần xác nhận sớm; xử lý FK error |
| Query ban đầu ít, vòng lặp tạo nhiều SELECT | N+1 do khởi tạo proxy từng entity | Join fetch, entity graph, batch fetching hoặc projection |
| `getClass()` không bằng class entity | Object là proxy subclass | Dùng type handling tương thích proxy; cân nhắc Hibernate.getClass() |
| `equals()` tải database | Equality truy cập lazy field/association | Dùng identity/natural key ổn định, không truy cập association |
| Log object gây SQL | `toString()` duyệt lazy fields | Giới hạn field trong toString/log DTO |
| Serializer gây LazyInitializationException | Serialize entity ngoài Session | Map DTO trước khi kết thúc transaction |
| One-to-one LAZY vẫn phát SQL sớm | Mapping optional/inverse hoặc provider limitation | Kiểm tra enhancement và SQL thực tế |
| Dùng proxy để bỏ qua authorization | Reference theo ID không xác nhận quyền | Kiểm tra tenant/permission/business state |
| Cast proxy sang subtype gây lỗi | Chưa biết runtime subtype hoặc proxy class khác | Query subtype/fetch state theo mapping |
| Collection vẫn chưa load sau initialize một proxy khác | Initialization không đệ quy cả graph | Tải đúng association cần thiết bằng fetch plan |

## 23. Cách quan sát proxy trong thực tế

```java
import org.hibernate.Hibernate;
import org.hibernate.Session;

try (Session session = sessionFactory.openSession()) {
    Customer customer = session.getReference(Customer.class, 7L);

    System.out.println(
            "initialized=" + Hibernate.isInitialized(customer));

    // Chỉ đọc identifier thường không cần khởi tạo proxy.
    System.out.println("id=" + customer.getId());

    System.out.println(
            "initialized=" + Hibernate.isInitialized(customer));

    // Truy cập field cần tải trạng thái entity.
    System.out.println("name=" + customer.getName());

    System.out.println(
            "initialized=" + Hibernate.isInitialized(customer));
}
```

Khi bật SQL logging, quan sát xem SELECT Customer xuất hiện ở thời điểm nào. Không nên dùng test này để khẳng định mọi getter ID trong mọi access strategy đều miễn phí; hãy xác nhận hành vi với mapping và Hibernate version của ứng dụng.

Một test cho association:

```java
try (Session session = sessionFactory.openSession()) {
    Order order = session.get(Order.class, 100L);

    System.out.println(
            Hibernate.isInitialized(order.getCustomer()));
    System.out.println(
            Hibernate.isInitialized(order.getLines()));

    String customerName = order.getCustomer().getName();
    System.out.println(customerName);
}
```

Test cho thấy proxy Customer và collection OrderLines có thể có trạng thái khởi tạo độc lập. Việc khởi tạo Customer không đồng nghĩa collection lines cũng được tải.

## 24. Sơ đồ quyết định khi làm việc với proxy

```text
                 Có association tới entity khác
                              │
                    Có cần state entity đích?
                       ┌──────┴──────┐
                      KHÔNG         CÓ
                       │             │
                       ▼             ▼
                Chỉ cần reference  Tải state trong Session?
                theo ID?               │
                  │               ┌────┴────┐
             ┌────┴────┐         CÓ       KHÔNG
            CÓ        KHÔNG       │         │
             │          │         ▼         ▼
             ▼          ▼      find()/   Mở transaction
       getReference()  Truyền ID  fetch   mới rồi query
             │                    │
             ▼                    ▼
      Proxy có thể chưa       Dùng DTO nếu
      khởi tạo                  rời tầng ORM
             │
             ▼
      Truy cập state?
        ┌────┴─────┐
       Session    Session
       còn mở     đã đóng
         │          │
         ▼          ▼
      SELECT và   LazyInitialization
      initialize  Exception có thể xảy ra
```

## 25. Những nguyên tắc cần nhớ

Proxy là đại diện lazy cho một entity theo identifier. Nó cho phép Hibernate trì hoãn SELECT cho tới khi ứng dụng cần trạng thái thật của entity. `getReference()` thường tạo cơ hội lấy reference mà không tải ngay, trong khi `find()` thường lấy entity state khi cần.

Proxy vẫn gắn với persistence context và Session. Nếu Session đóng khi proxy chưa khởi tạo, truy cập state có thể gây `LazyInitializationException`. Entity proxy khác với persistent collection wrapper; mỗi loại có trạng thái và cách khởi tạo riêng. Bytecode enhancement có thể hỗ trợ lazy loading ở cấp thuộc tính nhưng không nên bị nhầm với mọi cơ chế proxy.

Đừng để `equals()`, `hashCode()`, `toString()`, debugger hoặc JSON serializer vô tình truy cập lazy association. Hãy tải dữ liệu đúng use case bằng join fetch, entity graph, batch fetching hoặc projection. Khi chỉ cần ID để gán quan hệ, `getReference()` có thể tiết kiệm một SELECT; khi cần kiểm tra existence, authorization hoặc business state, hãy query dữ liệu cần thiết.

**Một proxy không phải một entity “chưa có dữ liệu” theo nghĩa thiếu identity; nó là một reference có identity nhưng chưa có state được tải.** Hiểu ranh giới đó giúp ứng dụng tận dụng lazy loading mà vẫn kiểm soát SQL, Session lifecycle và tính đúng đắn của nghiệp vụ.

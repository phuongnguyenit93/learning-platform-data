# Lazy loading, proxy và ảnh hưởng đến equals, hashCode

Trong ứng dụng Java dùng JPA/Hibernate, một entity có thể được tải theo cách trì hoãn (lazy loading). Thay vì đọc toàn bộ quan hệ ngay khi truy vấn, ORM có thể trả về một **proxy** hoặc collection wrapper đại diện cho dữ liệu chưa được nạp. Khi ứng dụng truy cập dữ liệu đó trong lúc persistence context còn hoạt động, Hibernate mới thực hiện truy vấn cần thiết.

Cơ chế này giúp tránh tải một object graph lớn khi chỉ cần một phần dữ liệu. Tuy nhiên, proxy có thể làm lộ ra khác biệt giữa lớp thực tế và lớp proxy, giữa object đã nạp và object chưa nạp. Nếu `equals()` hoặc `hashCode()` dựa vào `getClass()`, field chưa khởi tạo, quan hệ lazy hoặc ID chỉ được sinh sau khi persist, các entity tưởng như giống nhau có thể không bằng nhau hoặc có hash code thay đổi theo thời gian.

Bài viết giải thích cách lazy loading và proxy hoạt động, các lỗi thường gặp khi truy cập quan hệ, tác động đến equality/hash code và cách chọn chiến lược phù hợp cho entity trong mô hình DDD.

## 1. Lazy loading là gì?

Lazy loading là chiến lược chỉ tải một phần dữ liệu khi cần. Với JPA, quan hệ có thể được cấu hình `LAZY`; Hibernate thường tạo proxy cho quan hệ to-one hoặc collection wrapper cho quan hệ to-many.

Ví dụ một đơn hàng có khách hàng và nhiều dòng hàng:

```java
@Entity
public class OrderEntity {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private CustomerEntity customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private Set<OrderLineEntity> lines = new HashSet<>();
}
```

Khi truy vấn `OrderEntity`, ORM có thể chỉ tải hàng trong bảng `orders`. Quan hệ `customer` có thể được biểu diễn bằng proxy và `lines` bằng collection wrapper chưa nạp phần tử. Khi gọi `order.getCustomer().getName()` hoặc duyệt `order.getLines()`, Hibernate có thể phát sinh SQL để tải dữ liệu.

### 1.1. EAGER và LAZY không chỉ là hai tùy chọn hiệu năng

- **EAGER:** quan hệ cần được tải theo yêu cầu của mapping khi entity được lấy. ORM có thể dùng join hoặc truy vấn bổ sung; EAGER không đảm bảo chỉ có một câu SQL.
- **LAZY:** dữ liệu quan hệ có thể được trì hoãn cho đến khi truy cập. Cần một persistence context còn hoạt động để ORM tải dữ liệu nếu chưa được khởi tạo.

`LAZY` không có nghĩa là “chắc chắn không tải”, và `EAGER` không có nghĩa là “luôn join”. Cách tải thực tế phụ thuộc mapping, query, fetch plan, provider và phiên bản ORM.

Với JPA, `@ManyToOne` và `@OneToOne` mặc định EAGER theo đặc tả, còn `@OneToMany` và `@ManyToMany` mặc định LAZY. Nhiều nhóm chủ động khai báo fetch type và fetch plan để tránh phụ thuộc vào default. Với quan hệ to-one, dùng LAZY cần lưu ý khả năng hỗ trợ proxy/bytecode enhancement và hành vi cụ thể của provider.

### 1.2. Vì sao cần lazy loading?

Giả sử một màn hình chỉ hiển thị mã đơn và trạng thái. Nếu mỗi lần tải đơn đều kéo theo khách hàng, địa chỉ, tất cả dòng hàng, lịch sử thanh toán và lịch sử giao hàng, hệ thống sẽ đọc nhiều dữ liệu hơn mức cần thiết.

Lazy loading có thể giúp:

- Giảm số cột và quan hệ được tải khi không cần.
- Tránh tạo object graph lớn không cần thiết.
- Cho phép use case tải dữ liệu theo nhu cầu.
- Giảm chi phí truy vấn ở những luồng chỉ dùng một phần aggregate.

Nhưng lazy loading cũng có thể tạo ra nhiều truy vấn nhỏ nếu ứng dụng truy cập quan hệ trong vòng lặp. Vì vậy, cần thiết kế fetch plan theo use case thay vì coi lazy loading là giải pháp hiệu năng tự động.

## 2. Proxy trong Hibernate hoạt động như thế nào?

Proxy là một object đại diện cho entity chưa được nạp đầy đủ. Hibernate có thể tạo lớp proxy kế thừa entity class hoặc dùng cơ chế bytecode enhancement để trì hoãn tải dữ liệu. Proxy giữ thông tin định danh và biết cách tải trạng thái thật khi một thao tác cần dữ liệu chưa có.

Ví dụ:

```java
OrderEntity order = entityManager.find(OrderEntity.class, 100L);
CustomerEntity customer = order.getCustomer();
```

Tùy mapping và trạng thái persistence context, `customer` có thể là proxy. Việc lấy proxy chưa nhất thiết truy vấn toàn bộ hàng `customers`. Khi gọi một thuộc tính cần trạng thái thật, ORM mới khởi tạo proxy.

### 2.1. Proxy không nhất thiết có cùng class runtime với entity

Nếu entity class là `CustomerEntity`, object được trả về có thể có runtime class được Hibernate sinh ra, chẳng hạn một lớp con proxy. Vì thế:

```java
customer.getClass() == CustomerEntity.class
```

có thể là `false`, dù object đại diện cho một `CustomerEntity` có định danh cụ thể.

Đây là một trong những nguyên nhân khiến cách viết `equals()` bằng so sánh `getClass()` gặp vấn đề khi một bên là entity đã nạp và bên kia là proxy.

### 2.2. Truy cập ID và truy cập trạng thái khác nhau

Proxy thường có thể cung cấp identifier mà không cần tải toàn bộ entity. Tuy nhiên, truy cập các thuộc tính khác có thể khởi tạo proxy và phát sinh SQL. Chi tiết phụ thuộc provider, access strategy, enhancement và cách khai báo identifier.

Không nên giả định mọi getter đều miễn phí. Một phương thức tưởng như chỉ đọc có thể kích hoạt truy vấn nếu nó truy cập quan hệ lazy hoặc field chưa được nạp.

### 2.3. Collection wrapper cũng là proxy theo nghĩa thực dụng

Với `@OneToMany` hoặc `@ManyToMany`, Hibernate có thể thay `Set`/`List` thông thường bằng một implementation theo dõi trạng thái khởi tạo, dirty checking và thao tác persistence.

Ví dụ:

```java
Set<OrderLineEntity> lines = order.getLines();
```

Lấy tham chiếu collection chưa chắc đã tải các phần tử. Các thao tác như `size()`, `iterator()`, `contains()` hoặc duyệt collection có thể kích hoạt truy vấn, tùy loại collection và trạng thái đã nạp.

Vì collection wrapper thực hiện tracking, không nên thay thế hoặc sử dụng collection theo cách làm mất khả năng dirty checking mà ORM cần. Đồng thời, không nên để `equals()`/`hashCode()` của entity tự duyệt collection lazy.

## 3. Persistence context và vòng đời proxy

JPA persistence context quản lý các entity được load hoặc persist trong một đơn vị làm việc. Hibernate dùng context này để theo dõi identity, trạng thái và thay đổi của entity.

Một proxy chưa khởi tạo có thể tải dữ liệu khi persistence context còn mở. Nếu proxy được truy cập sau khi session/entity manager đã đóng, Hibernate không còn nơi thực hiện truy vấn.

### 3.1. LazyInitializationException

Ví dụ:

```java
OrderEntity order = orderRepository.findById(100L).orElseThrow();
entityManager.close();

int lineCount = order.getLines().size(); // Có thể ném LazyInitializationException
```

Lỗi xảy ra vì collection chưa được khởi tạo, nhưng persistence context đã đóng. Đây không phải lỗi dữ liệu không tồn tại; nó là lỗi truy cập trạng thái lazy ngoài phạm vi persistence context.

### 3.2. Không giải quyết bằng cách bật EAGER cho mọi quan hệ

Đổi mọi quan hệ sang EAGER có thể làm lỗi lazy biến mất ở một luồng nhưng gây tải dữ liệu thừa, join phức tạp hoặc N+1 ở luồng khác. Hãy tải đúng dữ liệu mà use case cần trong transaction, rồi chuyển thành DTO/read model trước khi rời persistence boundary.

Các cách phổ biến:

- JPQL `JOIN FETCH` cho một truy vấn cụ thể.
- JPA EntityGraph để khai báo fetch plan theo use case.
- Batch fetching hoặc subselect fetching tùy ORM và query pattern.
- Projection chỉ lấy field cần hiển thị.
- Application service hoàn thành việc đọc dữ liệu trong transaction rồi trả DTO thay vì trả entity có quan hệ lazy ra ngoài.

### 3.3. Open Session in View không thay thế fetch design

Open Session in View (OSIV) giữ persistence context mở trong suốt quá trình xử lý request web, cho phép view/serializer truy cập lazy association sau khi application service đã kết thúc. Điều này có thể che giấu lỗi lazy nhưng cũng khiến truy vấn database phát sinh ở tầng presentation và khó dự đoán.

Một response JSON có thể vô tình kích hoạt nhiều truy vấn khi serializer duyệt quan hệ. Hãy chủ động xác định dữ liệu cần trả và tải nó trong query/application boundary. OSIV là một lựa chọn kiến trúc cần đánh giá, không phải cách thay thế cho fetch plan rõ ràng.

## 4. N+1 query và tác động của lazy loading

N+1 xảy ra khi ứng dụng tải N entity bằng một truy vấn, sau đó phát sinh thêm một truy vấn cho mỗi entity để tải quan hệ.

Ví dụ:

```java
List<OrderEntity> orders = orderRepository.findRecentOrders();

for (OrderEntity order : orders) {
    System.out.println(order.getCustomer().getName());
}
```

Nếu truy vấn đầu lấy 50 đơn, truy cập `customer` có thể tạo thêm tối đa 50 truy vấn. Tổng số query là 1 + N.

### 4.1. Các cách xử lý

**Fetch join:**

```java
@Query("""
    select o
    from OrderEntity o
    join fetch o.customer
    where o.createdAt >= :from
    """)
List<OrderEntity> findRecentWithCustomer(Instant from);
```

**EntityGraph:**

```java
@EntityGraph(attributePaths = {"customer"})
List<OrderEntity> findByCreatedAtAfter(Instant from);
```

**Projection:**

```java
public record OrderListItem(
    Long id,
    String orderNumber,
    String customerName,
    OrderStatus status
) {}
```

Với màn hình chỉ cần tên khách hàng và trạng thái đơn, projection thường hiệu quả hơn tải toàn bộ aggregate và quan hệ.

### 4.2. Không fetch join bừa bãi collection khi phân trang

Fetch join collection có thể nhân bản dòng kết quả theo số phần tử trong collection, khiến việc phân trang phức tạp hoặc không được database/provider thực hiện như mong muốn. Một cách tiếp cận là phân trang ID trước rồi tải chi tiết cần thiết trong truy vấn thứ hai, hoặc dùng projection/batch fetching.

Hãy kiểm tra SQL thực tế và query plan. Một annotation không đảm bảo hiệu năng tốt nếu nó tải quá nhiều dữ liệu hoặc tạo kết quả nhân bản lớn.

## 5. equals() và hashCode() trong Java

`equals()` xác định hai object có được xem là bằng nhau theo semantics của class hay không. `hashCode()` cung cấp giá trị hash được các cấu trúc như `HashSet` và `HashMap` sử dụng.

Hợp đồng Java yêu cầu:

- Nếu `a.equals(b)` là `true`, thì `a.hashCode() == b.hashCode()` phải đúng.
- Trong một lần thực thi, hash code phải ổn định khi thông tin dùng để so sánh không thay đổi.
- `equals()` phải có tính phản xạ, đối xứng, bắc cầu, nhất quán và trả `false` với `null`.

Với entity ORM, việc tuân thủ hợp đồng này khó hơn vì ID có thể được sinh sau khi persist, proxy có runtime class khác entity thật và quan hệ lazy có thể kích hoạt SQL.

## 6. Vì sao getClass() có thể làm equals sai với proxy?

Một cách triển khai phổ biến:

```java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (other == null || getClass() != other.getClass()) return false;
    CustomerEntity that = (CustomerEntity) other;
    return Objects.equals(id, that.id);
}
```

Khi `this` là `CustomerEntity` đã nạp và `other` là proxy subclass, `getClass()` trả về hai class khác nhau. Hai object đại diện cùng một hàng database nhưng `equals()` trả `false`.

Đây là vấn đề đặc thù khi so sánh class runtime trong môi trường proxy. Nó không có nghĩa `getClass()` luôn sai trong Java; nó có nghĩa implementation phải tính đến proxy và inheritance strategy của ORM.

### 6.1. instanceof có thể giải quyết một phần, nhưng không phải lời giải phổ quát

Một số implementation dùng `instanceof`:

```java
if (!(other instanceof CustomerEntity that)) {
    return false;
}
```

Proxy subclass vẫn là một `CustomerEntity`, nên phép kiểm tra có thể hoạt động. Tuy nhiên, với entity inheritance, `instanceof` có thể coi hai subtype khác nhau là cùng kiểu cơ sở. Nếu domain yêu cầu phân biệt concrete subtype, cần chiến lược so sánh type nhất quán và proxy-aware.

Không nên thay `getClass()` bằng `instanceof` một cách máy móc mà không xem xét entity inheritance, proxy provider và semantics định danh trong domain.

### 6.2. Tránh gọi method làm khởi tạo proxy trong equals

Nếu `equals()` truy cập quan hệ lazy hoặc gọi getter có side effect tải dữ liệu, phép so sánh có thể phát sinh SQL hoặc ném `LazyInitializationException` khi session đóng.

`equals()` và `hashCode()` nên tránh:

- Duyệt collection lazy.
- So sánh toàn bộ object graph.
- Gọi method tính toán cần truy cập database.
- Dùng association hai chiều như `order.getCustomer().getOrders()`.
- Dùng field mutable thay đổi theo vòng đời.

Equality của entity nên dựa vào định danh ổn định hoặc business key được chọn có chủ đích, không dựa vào mọi field của object.

## 7. ID được sinh sau khi persist và hashCode thay đổi

Một vấn đề quan trọng khác là generated ID. Trước khi persist, entity có thể có `id == null`; sau khi insert, database/ORM gán ID.

Nếu `hashCode()` phụ thuộc trực tiếp vào ID, giá trị hash thay đổi sau khi entity đã được thêm vào `HashSet` hoặc dùng làm key trong `HashMap`.

```java
OrderEntity order = new OrderEntity(); // id = null
Set<OrderEntity> orders = new HashSet<>();
orders.add(order);

entityManager.persist(order); // id được sinh

orders.contains(order); // Có thể trả false nếu hashCode đã đổi
```

`HashSet` đặt object vào bucket dựa trên hash code tại thời điểm add. Nếu hash code thay đổi, object nằm ở bucket cũ nhưng lookup tìm bucket mới.

### 7.1. Không dùng field mutable làm hash key

Ngoài ID được sinh muộn, các field như `status`, `updatedAt`, `name` hoặc quan hệ có thể thay đổi. Nếu chúng tham gia `hashCode()`, việc cập nhật entity sau khi thêm vào `HashSet` có thể làm hỏng khả năng tìm kiếm.

Một nguyên tắc quan trọng: các thuộc tính dùng trong equality/hash code phải ổn định trong thời gian object được sử dụng làm key trong hash-based collection.

## 8. Chọn identity hay business key?

DDD phân biệt entity với value object. Entity có identity liên tục qua các thay đổi; value object được xác định bằng giá trị. Vì vậy, equality của entity thường dựa trên identity hoặc một business key thực sự ổn định, còn equality của value object dựa trên toàn bộ giá trị cấu thành.

### 8.1. So sánh theo generated database ID

Ưu điểm:

- ID duy nhất trong phạm vi được xác định.
- Hai instance được tải ở hai persistence context khác nhau có thể được nhận diện là cùng entity.
- Không cần so sánh toàn bộ trạng thái mutable.

Hạn chế:

- Entity mới chưa có ID.
- ID có thể được gán muộn tùy generation strategy.
- Cần xử lý proxy và inheritance.
- Không nên coi hai entity mới có `id == null` là bằng nhau.

Một quy tắc thường dùng là hai entity khác reference chỉ bằng nhau khi cả hai có ID khác null và ID bằng nhau. Hai entity mới chưa có ID không bằng nhau, trừ khi cùng reference.

### 8.2. So sánh theo natural/business key

Business key là một thuộc tính hoặc tập thuộc tính có ý nghĩa nghiệp vụ và ổn định, ví dụ mã đăng ký quốc gia hoặc mã hợp đồng bất biến trong phạm vi domain.

Ưu điểm:

- Có thể xác định equality trước khi database sinh ID.
- Hash code ổn định nếu key bất biến.
- Phản ánh identity mà nghiệp vụ nhận biết.

Rủi ro:

- Key có thể không thực sự duy nhất.
- Key có thể thay đổi theo chính sách hoặc sửa dữ liệu.
- So sánh key có thể cần normalize và thống nhất case/format.
- Một business key có thể chỉ duy nhất trong tenant hoặc bounded context, cần đưa scope vào equality.

Không dùng email, tên hiển thị hoặc số điện thoại làm business key bất biến nếu nghiệp vụ cho phép thay đổi chúng.

### 8.3. Dùng object identity mặc định

Nếu ứng dụng chỉ so sánh entity trong cùng một persistence context và không cần nhận diện hai instance đại diện cùng hàng qua session khác nhau, implementation mặc định của `Object.equals()` có thể đủ. Đừng override equals/hashCode chỉ vì entity có ID.

Khi entity đi qua nhiều persistence context, được detach/merge hoặc dùng trong Set/Map lâu dài, hãy xác định rõ semantics cần có rồi mới chọn implementation.

## 9. Chiến lược equals/hashCode thường dùng cho entity có generated ID

Không có một implementation duy nhất phù hợp mọi ORM, inheritance mapping và ID strategy. Với entity đơn giản, không có entity inheritance phức tạp, một cách thường gặp là:

- `equals()` trả true ngay nếu cùng reference.
- Chỉ so sánh với cùng loại entity theo semantics đã chọn; proxy subclass phải được chấp nhận.
- Hai object khác reference chỉ bằng nhau khi ID của cả hai đã được gán và bằng nhau.
- `hashCode()` dùng giá trị ổn định trước và sau khi ID được gán.
- Không truy cập association lazy.

Ví dụ minh họa cho một entity cụ thể, không có inheritance nghiệp vụ:

```java
@Entity
public class CustomerEntity {
    @Id
    @GeneratedValue
    private Long id;

    protected CustomerEntity() {}

    public Long getId() {
        return id;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof CustomerEntity that)) {
            return false;
        }
        Long thisId = getId();
        Long otherId = that.getId();
        return thisId != null && thisId.equals(otherId);
    }

    @Override
    public int hashCode() {
        return CustomerEntity.class.hashCode();
    }
}
```

`hashCode()` cố định theo entity class để không thay đổi khi ID được sinh. Proxy subclass vẫn dùng cùng giá trị hash được trả từ implementation này. Cách làm này có thể tạo nhiều collision vì mọi customer cùng class có cùng hash code; `HashSet` vẫn đúng về mặt hợp đồng nhưng hiệu năng có thể giảm khi tập hợp rất lớn.

Đoạn mã chỉ minh họa chiến lược cho một entity cụ thể. Với inheritance, nhiều class proxy, composite ID hoặc provider khác Hibernate, cần kiểm chứng equality và hash code trên đúng mapping thực tế. Có thể cần một base class được thiết kế cẩn thận hoặc Hibernate-specific class resolution, nhưng việc dùng API ORM trong entity sẽ tạo coupling cần cân nhắc.

### 9.1. Vì sao không dùng `id.hashCode()` trực tiếp?

Nếu ID null trước khi persist, implementation có thể trả một giá trị khác hoặc gây lỗi. Sau khi persist, hash code thay đổi. Điều này vi phạm yêu cầu ổn định khi entity đang nằm trong hash-based collection.

### 9.2. Vì sao không dùng `Objects.hash(id)`?

`Objects.hash(id)` vẫn phụ thuộc vào ID. Nó không giải quyết vấn đề ID được sinh muộn; chỉ là cách viết gọn hơn.

### 9.3. Hash code cố định có làm Set sai không?

Không. Hash-based collection dùng hash code để chọn bucket và dùng `equals()` để phân biệt phần tử. Nhiều object cùng hash code vẫn được lưu chính xác, chỉ có thể làm hiệu năng giảm khi collision nhiều.

## 10. Chiến lược natural key

Nếu domain có một business key thực sự bất biến, đây thường là lựa chọn tốt cho equality.

Ví dụ một `CountryCode` value object có thể so sánh theo mã ISO đã chuẩn hóa. Với entity `TaxRegistration`, nếu mã đăng ký là duy nhất và không thể đổi trong phạm vi quốc gia, có thể dùng cặp `(countryCode, registrationNumber)` làm business key.

```java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (!(other instanceof TaxRegistration that)) return false;
    return countryCode.equals(that.getCountryCode())
        && registrationNumber.equals(that.getRegistrationNumber());
}

@Override
public int hashCode() {
    return Objects.hash(countryCode, registrationNumber);
}
```

Ví dụ chỉ an toàn nếu hai thuộc tính là immutable, không lazy và đã được thiết lập trước khi object được đưa vào collection. Nếu chúng mutable hoặc có thể chưa được nạp ở proxy, cần chọn cách khác.

Không nên gọi một business key là “natural” chỉ vì nó trông có vẻ duy nhất. Hãy xác nhận với domain expert rằng nó không đổi, có phạm vi uniqueness rõ và có ý nghĩa identity trong nghiệp vụ.

## 11. Quan hệ hai chiều và vòng lặp equals/hashCode

Một entity `Order` có thể tham chiếu `Customer`, còn `Customer` có collection `orders`. Nếu Lombok `@Data` hoặc implementation tự động đưa tất cả field vào `equals()`, `hashCode()` và `toString()`, việc so sánh có thể đi theo vòng:

```text
Order.equals()
  -> Customer.equals()
      -> Customer.orders.equals()
          -> Order.equals()
              -> ...
```

Điều này có thể gây recursion vô hạn, tải lazy collection ngoài ý muốn hoặc phát sinh hàng loạt truy vấn.

### 11.1. Không đưa association vào equality

Equality của entity nên dựa vào identity hoặc business key, không dựa vào quan hệ hai chiều. Tránh đưa `@OneToMany`, `@ManyToMany` hoặc association lazy vào `equals()`/`hashCode()`.

### 11.2. Cẩn thận với Lombok `@Data`

`@Data` sinh getter, setter, `equals()`, `hashCode()` và `toString()` dựa trên field theo cấu hình. Với JPA entity có quan hệ lazy và field mutable, đây thường không phải lựa chọn an toàn.

Có thể dùng `@Getter`/`@Setter` có chọn lọc, rồi tự định nghĩa equals/hashCode. Nếu dùng `@EqualsAndHashCode`, cần khai báo rõ field được đưa vào và kiểm thử với proxy, detached entity và entity mới.

### 11.3. toString cũng có thể kích hoạt lazy loading

Logging một entity không nên vô tình duyệt toàn bộ quan hệ. `toString()` nên tránh association và dữ liệu nhạy cảm. Log ID hoặc business key cần thiết thay vì serialize object graph.

## 12. Proxy, inheritance và equals đối xứng

Hợp đồng `equals()` yêu cầu đối xứng: nếu `a.equals(b)` là true thì `b.equals(a)` cũng phải true. Proxy và entity inheritance có thể làm điều này khó bảo đảm.

Ví dụ, một class cơ sở `Payment` có các subtype `CardPayment` và `BankTransfer`. Nếu `Payment.equals()` dùng `instanceof Payment` và chỉ so sánh ID, hai subtype khác nhau có thể bị coi là bằng nhau. Nếu dùng `getClass()`, proxy subclass có thể bị xem là khác class.

Các hướng xử lý:

- Tránh entity inheritance nếu nó không phản ánh mô hình domain cần thiết.
- Xác định equality theo aggregate/entity type và identity có phạm vi rõ.
- Nếu cần phân biệt subtype, dùng chiến lược class resolution tương thích proxy và kiểm tra tính đối xứng.
- Với Hibernate, có thể tham khảo API lấy persistent class từ proxy/lazy initializer; cần lưu ý một số cách lấy class có thể khởi tạo proxy và tạo truy vấn.
- Không tự viết một `instanceof` tổng quát cho mọi hierarchy mà chưa kiểm tra semantics domain.

Trong nhiều hệ thống, tách các subtype thành aggregate/entity riêng hoặc dùng composition sẽ đơn giản hóa equality và persistence mapping hơn một hierarchy sâu.

## 13. Proxy và cách truy cập field trong entity

JPA cho phép access theo field hoặc property, tùy vị trí annotation và mapping. Với property access, ORM sử dụng getter/setter; với field access, ORM truy cập field theo cơ chế provider. Proxy subclass thường override method để intercept thao tác, còn bytecode enhancement có thể thay đổi cách tải thuộc tính.

Một implementation equality đọc trực tiếp field có thể hoạt động khác khi `this` hoặc `other` là proxy. Nếu dùng getter, getter identifier có thể được proxy xử lý mà không tải toàn bộ entity, nhưng không nên khái quát cho mọi field hoặc mọi provider.

Hãy kiểm tra các trường hợp:

- Entity thường so sánh với entity thường.
- Entity đã nạp so sánh với proxy chưa khởi tạo.
- Proxy chưa khởi tạo so sánh với entity đã nạp.
- Hai proxy đại diện cùng ID.
- Hai entity mới chưa có ID.
- Entity detached so sánh với entity được tải trong persistence context khác.
- Subtype và superclass nếu có inheritance.

Test nên xác minh cả `a.equals(b)` và `b.equals(a)`, hash code và trạng thái khởi tạo của proxy sau phép so sánh.

## 14. Lazy loading trong DDD: domain model và persistence model

Trong DDD, aggregate là ranh giới nhất quán và domain model biểu đạt hành vi nghiệp vụ. Proxy ORM là chi tiết persistence. Nếu entity domain bị phụ thuộc trực tiếp vào lazy proxy, việc gọi một phương thức domain có thể phát sinh truy vấn hoặc lỗi khi session đã đóng.

Có hai hướng tổ chức thường gặp:

### 14.1. Dùng JPA entity trực tiếp làm domain entity

Hướng này giảm mapping và số class. Tuy nhiên, cần kỷ luật:

- Không để domain method truy cập quan hệ lazy ngoài fetch plan đã xác định.
- Không để equals/hashCode/toString duyệt association.
- Không trả entity ra API hoặc view sau khi transaction đóng.
- Kiểm soát constructor, setter và proxy requirement của ORM.
- Test hành vi với persistence context thật.

### 14.2. Tách persistence model khỏi domain model

Persistence adapter tải JPA entity, map sang domain aggregate thuần, application/domain thực hiện hành vi, sau đó mapper chuyển thay đổi về persistence model.

Ưu điểm là domain không biết proxy, lazy collection hoặc annotation ORM. Đổi lại, nhóm phải duy trì mapper, quản lý thay đổi và cân nhắc chi phí tải graph.

Không có một lựa chọn đúng cho mọi dự án. Khi domain phức tạp và cần độc lập framework, tách model có thể đáng giá. Với ứng dụng CRUD đơn giản, dùng chung entity có thể hợp lý nếu ORM không làm méo mô hình.

## 15. Chiến lược thực hành an toàn

Một bộ nguyên tắc thực tế:

1. **Chọn identity có chủ đích.** Dùng object identity, generated ID hoặc immutable business key tùy semantics.
2. **Không so sánh toàn bộ field.** Tránh mutable state và association lazy trong equals/hashCode.
3. **Không để hash code đổi sau persist.** Đặc biệt khi ID được sinh muộn và entity có thể nằm trong Set/Map.
4. **Xử lý proxy rõ ràng.** Tránh `getClass()` máy móc; `instanceof` cũng cần cân nhắc inheritance.
5. **Không truy cập quan hệ lazy trong equality.** Equality nên nhanh, xác định và không tạo I/O.
6. **Đừng dùng `@Data` cho entity JPA một cách mặc định.** Kiểm soát equals/hashCode/toString riêng.
7. **Tải dữ liệu theo use case.** Fetch join, EntityGraph, batch fetching hoặc projection phù hợp.
8. **Không trả entity lazy ra ngoài persistence boundary.** Chuyển thành DTO/read model trong transaction.
9. **Kiểm thử trên ORM thực tế.** Proxy, ID generation và inheritance có thể khác nhau giữa provider/version.

## 16. Bộ test mẫu cho equals/hashCode

Với chiến lược generated ID, test cần bao gồm entity mới và entity đã có ID:

```java
class CustomerEntityEqualityTest {
    @Test
    void sameReferenceIsEqualBeforePersist() {
        CustomerEntity customer = new CustomerEntity();

        assertEquals(customer, customer);
    }

    @Test
    void twoNewEntitiesAreNotEqual() {
        CustomerEntity first = new CustomerEntity();
        CustomerEntity second = new CustomerEntity();

        assertNotEquals(first, second);
    }

    @Test
    void hashCodeDoesNotChangeWhenIdIsAssigned() {
        CustomerEntity customer = new CustomerEntity();
        int beforePersist = customer.hashCode();

        customer.assignIdForTest(10L);

        assertEquals(beforePersist, customer.hashCode());
    }
}
```

Test trên là minh họa và cần điều chỉnh theo cách ID được gán trong dự án. Với proxy, cần integration test:

```java
CustomerEntity loaded = entityManager.find(CustomerEntity.class, id);
entityManager.clear();

CustomerEntity proxy = entityManager.getReference(CustomerEntity.class, id);

assertTrue(loaded.equals(proxy));
assertTrue(proxy.equals(loaded));
assertEquals(loaded.hashCode(), proxy.hashCode());
```

Trong test thực tế, đảm bảo `proxy` chưa bị khởi tạo trước khi gọi equals nếu mục tiêu là kiểm tra proxy chưa nạp. Có thể kiểm tra trạng thái bằng API persistence phù hợp, ví dụ `PersistenceUnitUtil.isLoaded()` hoặc API Hibernate. Sau đó kiểm tra phép so sánh không gây truy vấn ngoài dự kiến.

### 16.1. Kiểm tra hash-based collection

```java
Set<CustomerEntity> customers = new HashSet<>();
CustomerEntity customer = new CustomerEntity();
customers.add(customer);

// Sau khi persist và ID được gán:
assertTrue(customers.contains(customer));
```

Nếu entity có hash code thay đổi sau persist, test này có thể thất bại. Hãy bổ sung test khi entity được detach, merge hoặc tải lại ở persistence context khác nếu hệ thống cần so sánh qua các context.

## 17. Sai lầm thường gặp

**Cho rằng LAZY luôn nhanh hơn EAGER.** Lazy loading có thể tạo N+1 và nhiều round trip. Fetch plan phải theo use case và được đo bằng SQL thực tế.

**Bật EAGER để sửa LazyInitializationException.** Điều này có thể tải dữ liệu thừa ở mọi luồng. Hãy tải dữ liệu cần thiết trong transaction bằng fetch join, EntityGraph hoặc projection.

**So sánh `getClass()` mà không xét proxy.** Runtime class của proxy có thể khác entity class, làm hai object cùng identity không bằng nhau.

**Dùng `instanceof` mà không xét inheritance.** Hai subtype có thể bị coi là cùng loại nếu chỉ so sánh ID của base class.

**Dùng generated ID trực tiếp cho hashCode khi ID có thể null.** Hash code thay đổi sau persist và làm hỏng lookup trong `HashSet`/`HashMap`.

**Dùng tất cả field trong equals/hashCode.** Mutable field và association lazy khiến equality thay đổi hoặc phát sinh truy vấn.

**Dùng Lombok `@Data` trên entity có quan hệ.** Generated equality và toString có thể duyệt object graph, gây recursion và N+1.

**Cho rằng equals không thể gây database query.** Nếu implementation truy cập getter/association lazy, phép so sánh có thể khởi tạo proxy.

**Không kiểm thử với proxy thật.** Unit test tạo hai object Java thường không phát hiện khác biệt runtime class hoặc lazy initialization.

**Để entity ORM thoát khỏi persistence boundary.** Serializer hoặc UI có thể vô tình tải lazy association sau khi transaction đóng.

## 18. Checklist thiết kế

Trước khi hoàn tất mapping entity và equality, hãy kiểm tra:

- Quan hệ nào cần LAZY và use case nào cần tải quan hệ đó?
- Fetch plan có tránh N+1 và tải object graph thừa không?
- Entity có bị trả ra ngoài khi persistence context đã đóng không?
- Equality của entity dựa trên identity hay business key nào?
- Business key có thật sự duy nhất, bất biến và không lazy không?
- Nếu dùng generated ID, hai entity mới có bị coi nhầm là bằng nhau không?
- Hash code có ổn định trước và sau khi ID được gán không?
- `equals()` có xử lý proxy và entity inheritance theo semantics rõ ràng không?
- `equals()`/`hashCode()` có tránh association và mutable field không?
- `toString()` có tránh quan hệ lazy và dữ liệu nhạy cảm không?
- Có dùng Lombok `@Data` hoặc generated equality cần rà soát không?
- Test có bao gồm entity thường, proxy, detached entity và HashSet/HashMap không?
- Test có xác minh phép so sánh không kích hoạt truy vấn ngoài dự kiến không?

## 19. Câu hỏi tự kiểm tra

1. Lazy loading là gì và Hibernate có thể dùng proxy để trì hoãn tải entity như thế nào?
2. Vì sao runtime class của proxy có thể khác class entity được khai báo?
3. LazyInitializationException xảy ra trong điều kiện nào?
4. N+1 query phát sinh như thế nào khi truy cập quan hệ lazy trong vòng lặp?
5. Vì sao `getClass()` trong equals có thể làm proxy và entity thật không bằng nhau?
6. Tại sao thay `getClass()` bằng `instanceof` không giải quyết mọi trường hợp inheritance?
7. Vì sao hashCode dựa trên generated ID có thể thay đổi sau persist và ảnh hưởng HashSet?
8. Khi nào business key phù hợp hơn database ID để xác định equality?
9. Vì sao không nên đưa collection lazy hoặc association hai chiều vào equals/hashCode?
10. Những test nào cần có để xác minh equality với proxy chưa khởi tạo?

## Kết luận

Lazy loading và proxy giúp ORM trì hoãn việc tải dữ liệu, nhưng chúng làm cho entity có thể khác biệt về runtime class và trạng thái khởi tạo. Vì vậy, `equals()` và `hashCode()` cần dựa trên identity hoặc business key ổn định, không phụ thuộc association lazy hay field mutable. Với generated ID, phải tránh để hash code thay đổi sau persist; với proxy và inheritance, cần kiểm tra tính đối xứng và semantics loại entity trên ORM thực tế. Fetch plan nên được thiết kế theo use case, và entity lazy không nên thoát khỏi persistence boundary. Khi hiểu rõ các tương tác này, nhóm có thể dùng ORM mà vẫn giữ được hành vi entity nhất quán và mô hình miền dễ kiểm soát.

# Đánh giá đối tượng ORM có dữ liệu tải chậm và tài nguyên đã đóng

Khi Jackson serialize một entity JPA/Hibernate, nó không chỉ đọc những field đang nằm sẵn trong object. Thông thường, Jackson gọi getter để lấy giá trị các property. Nếu getter trả về một Hibernate proxy hoặc một collection tải chậm, thao tác serialize có thể kích hoạt truy vấn SQL. Nếu persistence context đã đóng, việc truy cập dữ liệu lazy có thể thất bại với `LazyInitializationException`. Nếu property đại diện cho một tài nguyên như `Blob`, `Clob`, `InputStream` hoặc stream lấy từ JDBC, việc đọc nó sau khi tài nguyên đã đóng cũng có thể gây lỗi hoặc tạo payload không đầy đủ.

Vì vậy, serialize entity ORM cần được xem là một ranh giới giữa persistence và API. Ứng dụng phải quyết định dữ liệu nào được tải, tải ở thời điểm nào, dữ liệu nào được phép xuất và tài nguyên nào còn hợp lệ trong lúc Jackson đọc chúng. Cách an toàn thường là lấy dữ liệu theo fetch plan rõ ràng rồi ánh xạ sang DTO trong transaction; Jackson serialize DTO sau đó mà không phải tự truy cập persistence context.

## 1. Vì sao entity ORM không giống một object Java thông thường?

Một entity Hibernate có thể chứa các thuộc tính chưa được tải từ database. Hibernate dùng proxy và collection wrapper để trì hoãn việc truy vấn cho đến khi ứng dụng thực sự truy cập dữ liệu.

Ví dụ entity:

```java
@Entity
public class Order {
    @Id
    private Long id;

    private String orderNumber;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderItem> items = new ArrayList<>();

    // getters/setters
}
```

Khi truy vấn `Order`, Hibernate có thể tải `id` và `orderNumber` trước, nhưng chưa tải `customer` hoặc `items`. Thay vào đó, nó giữ một proxy hoặc một persistent collection biết cách tải dữ liệu khi cần.

Trạng thái khái quát:

```text
Order entity
  |
  +-- id, orderNumber       đã có trong memory
  +-- customer              proxy có thể chưa initialize
  +-- items                 PersistentCollection có thể chưa initialize
```

Điều này giúp ứng dụng không phải tải toàn bộ quan hệ của entity ngay khi truy vấn. Nhưng nó cũng có nghĩa entity có thể cần một `Session` hoặc `EntityManager` còn mở để hoàn tất việc đọc dữ liệu.

## 2. Jackson có thể kích hoạt lazy loading khi serialize

Jackson thường introspect property và gọi getter để lấy giá trị. Khi getter trả về association lazy, việc đọc giá trị tiếp theo có thể kích hoạt Hibernate.

Ví dụ:

```java
Order order = orderRepository.findById(orderId).orElseThrow();

String json = objectMapper.writeValueAsString(order);
```

Nếu mapper nhìn thấy `getCustomer()` và `getItems()`, nó có thể truy cập cả hai property trong lúc serialize. Với association chưa được initialize và session vẫn mở, Hibernate có thể phát sinh SQL để tải chúng.

Điều đó tạo ra một số hệ quả:

- Serialize có thể thực hiện truy vấn database mà code gọi mapper không nhận ra.
- Một object graph sâu có thể kéo theo nhiều truy vấn.
- Collection lớn có thể được tải toàn bộ chỉ vì API trả entity.
- Quan hệ hai chiều có thể tạo vòng tham chiếu khi Jackson đi từ parent sang child rồi quay lại parent.
- Nếu session đã đóng, getter có thể ném `LazyInitializationException`.

Jackson không tự biết association nào là cần thiết cho API. Nó chỉ nhìn thấy property có thể serialize theo cấu hình. Fetch plan và contract output phải được ứng dụng quyết định.

## 3. Session, persistence context và trạng thái detached

Trong JPA, `EntityManager` quản lý persistence context. Trong Hibernate, `Session` là đơn vị làm việc tương ứng. Entity được quản lý trong persistence context có thể dùng cơ chế lazy loading khi association chưa được tải.

Khi entity rời khỏi persistence context, nó trở thành detached. Những field đã được tải vẫn có thể đọc như object Java bình thường. Nhưng association lazy chưa initialize không còn môi trường để thực hiện truy vấn.

Một luồng thường gặp trong ứng dụng web:

```text
Controller gọi service
       |
       v
Service mở transaction / persistence context
       |
       v
Repository tải entity và một phần quan hệ
       |
       v
Service trả entity ra ngoài
       |
       v
Transaction/persistence context kết thúc
       |
       v
Jackson serialize response
       |
       v
Getter chạm vào association lazy chưa tải
       |
       v
LazyInitializationException
```

Không phải mọi trường hợp kết thúc transaction đều lập tức đóng session: một số ứng dụng dùng Open Session in View hoặc persistence context được quản lý rộng hơn. Nhưng không nên dựa vào việc session tình cờ còn mở để API hoạt động. Hợp đồng service nên bảo đảm dữ liệu cần serialize đã được chuẩn bị trước khi entity rời khỏi tầng persistence.

## 4. LazyInitializationException là gì?

`LazyInitializationException` là lỗi Hibernate thường gặp khi ứng dụng cố truy cập dữ liệu lazy mà không còn session/persistence context hợp lệ để tải dữ liệu.

Ví dụ:

```java
Order order;

try (Session session = sessionFactory.openSession()) {
    order = session.find(Order.class, orderId);
}

// Session đã đóng. Nếu items chưa được tải, truy cập có thể thất bại.
int itemCount = order.getItems().size();
```

Nếu `items` đã được initialize trong session, `size()` có thể hoạt động vì dữ liệu đã nằm trong memory. Nếu chưa, Hibernate cần session để chạy SQL và sẽ ném lỗi.

Trong lúc Jackson serialize, stack trace có thể chỉ ra getter của entity hoặc collection wrapper. Điều đó không có nghĩa Jackson làm hỏng entity; Jackson chỉ là thành phần đầu tiên chạm vào property lazy sau khi persistence context đã đóng.

## 5. Vì sao Open Session in View có thể che giấu vấn đề?

Một số ứng dụng web giữ `EntityManager`/Hibernate session mở trong suốt thời gian xử lý request, kể cả giai đoạn render response. Pattern này thường được gọi là Open Session in View (OSIV).

Khi OSIV đang hoạt động, Jackson có thể truy cập association lazy sau khi service transaction đã kết thúc và Hibernate vẫn còn session để tải dữ liệu. Vì thế, endpoint có thể không ném `LazyInitializationException`, nhưng SQL lại phát sinh trong giai đoạn serialize response.

Rủi ro:

- Truy vấn database bị ẩn trong quá trình ghi JSON.
- Một endpoint có thể tạo N+1 queries.
- Thời gian giữ connection/session có thể dài hơn dự kiến.
- Payload vô tình mở rộng khi một getter hoặc annotation mới được thêm vào.
- Hiệu năng phụ thuộc việc Jackson truy cập property theo cách nào.

OSIV có thể là một quyết định kiến trúc của ứng dụng, nhưng không nên dùng nó như cách chữa mặc định cho entity serialization. Ngay cả khi session còn mở, API vẫn cần fetch plan và DTO rõ ràng để kiểm soát số truy vấn và dữ liệu được xuất.

## 6. N+1 query khi Jackson đi qua quan hệ lazy

Giả sử endpoint trả về danh sách 50 đơn hàng. Truy vấn ban đầu lấy 50 `Order`, nhưng `customer` của từng đơn hàng chưa được tải. Khi Jackson serialize từng order và gọi `getCustomer()`, Hibernate có thể chạy thêm một truy vấn cho mỗi order.

```text
1 query: tải 50 Order
50 queries: tải Customer cho từng Order
-----------------------------------------
51 queries tổng cộng (mô hình minh họa)
```

Nếu mỗi order còn có `items`, `product` hoặc quan hệ khác, số truy vấn có thể tăng thêm. Đây là N+1 query problem.

N+1 có thể xảy ra dù endpoint không gọi repository trong vòng lặp. Việc Jackson gọi getter cũng có thể kích hoạt truy vấn. Đó là lý do cần kiểm tra SQL trong quá trình serialize hoặc tốt hơn là không để serialize entity quyết định fetch plan.

## 7. Cách ưu tiên: ánh xạ entity sang DTO trong transaction

DTO (Data Transfer Object) chỉ chứa dữ liệu mà API cần xuất. Service truy vấn entity, tải các quan hệ cần thiết và ánh xạ thành DTO trong khi persistence context còn mở.

Ví dụ DTO:

```java
public record OrderItemDto(
        Long productId,
        String productName,
        int quantity
) {
}

public record OrderDto(
        Long id,
        String orderNumber,
        String customerName,
        List<OrderItemDto> items
) {
}
```

Service thực hiện mapping trong transaction:

```java
@Service
public class OrderQueryService {
    private final OrderRepository orderRepository;

    public OrderQueryService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(readOnly = true)
    public OrderDto getOrder(Long orderId) {
        Order order = orderRepository.findDetailedById(orderId)
                .orElseThrow(() -> new EntityNotFoundException("Order not found"));

        List<OrderItemDto> items = order.getItems().stream()
                .map(item -> new OrderItemDto(
                        item.getProduct().getId(),
                        item.getProduct().getName(),
                        item.getQuantity()
                ))
                .toList();

        return new OrderDto(
                order.getId(),
                order.getOrderNumber(),
                order.getCustomer().getName(),
                items
        );
    }
}
```

Controller chỉ trả DTO:

```java
@GetMapping("/orders/{id}")
public OrderDto getOrder(@PathVariable Long id) {
    return orderQueryService.getOrder(id);
}
```

Jackson lúc này serialize `OrderDto`, không cần gọi getter trên entity Hibernate. DTO chứa các giá trị đã được lấy trong transaction, nên vòng đời của response không phụ thuộc session ORM.

Mapping DTO trong transaction không tự động giải quyết N+1. Fetch plan vẫn cần được thiết kế để những getter dùng trong mapper không phát sinh một truy vấn cho mỗi entity.

## 8. Tải đúng dữ liệu bằng fetch join

Với JPQL, có thể dùng `JOIN FETCH` để tải association cần thiết trong cùng truy vấn:

```java
@Query("""
       select o
       from Order o
       join fetch o.customer
       left join fetch o.items i
       left join fetch i.product
       where o.id = :id
       """)
Optional<Order> findDetailedById(@Param("id") Long id);
```

Truy vấn này tải customer, items và product của từng item khi lấy order. Service có thể ánh xạ các giá trị cần thiết sang DTO trong transaction.

Lưu ý khi dùng fetch join:

- Fetch join collection có thể nhân số dòng SQL theo số phần tử collection; Hibernate hợp nhất kết quả thành entity graph.
- Không nên fetch join nhiều collection song song nếu có thể tạo tích Descartes lớn hoặc gặp giới hạn bag của Hibernate.
- Fetch join collection kết hợp pagination có thể gây hành vi không mong muốn hoặc buộc Hibernate xử lý phân trang trong memory tùy phiên bản/cấu hình. Với danh sách lớn, hãy phân trang root entity trước rồi tải quan hệ theo chiến lược phù hợp.
- Chỉ fetch những quan hệ cần cho use case hiện tại; không tải toàn bộ object graph chỉ để tránh lazy exception.

Với một order đơn lẻ, fetch join một collection thường dễ kiểm soát. Với danh sách order phân trang, có thể dùng hai bước: truy vấn page ID/root trước, rồi truy vấn các association cần thiết cho tập ID đó.

## 9. Sử dụng JPA EntityGraph

JPA `EntityGraph` mô tả những association cần tải cho một truy vấn. Với Spring Data JPA, có thể khai báo:

```java
public interface OrderRepository extends JpaRepository<Order, Long> {
    @EntityGraph(attributePaths = {"customer", "items", "items.product"})
    @Query("select o from Order o where o.id = :id")
    Optional<Order> findDetailedById(@Param("id") Long id);
}
```

EntityGraph giúp tách fetch plan khỏi câu JPQL và thể hiện rõ quan hệ cần dùng. Provider có thể thực hiện bằng join hoặc các truy vấn bổ sung tùy mapping và cách triển khai. Hãy quan sát SQL thực tế để biết số truy vấn, thay vì giả định EntityGraph luôn tạo đúng một câu SQL.

EntityGraph cũng nên gắn với use case cụ thể. Một graph cho màn hình chi tiết có thể khác graph cho màn hình danh sách. Không nên tạo một graph khổng lồ dùng chung cho mọi endpoint.

## 10. Batch fetching và các lựa chọn khác

Nếu không thể tải tất cả association trong một fetch join, Hibernate có thể gom các lần tải lazy thành batch. Có thể cấu hình `@BatchSize` hoặc batch fetch size ở cấu hình Hibernate:

```java
@BatchSize(size = 25)
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderItem> items;
```

Batch fetching có thể giảm số truy vấn so với N+1, nhưng nó không thay thế việc xác định dữ liệu API cần. Nếu serialize entity graph không kiểm soát, Jackson vẫn có thể truy cập nhiều association hơn dự kiến.

Các lựa chọn fetch thường dùng:

| Cơ chế | Mục đích | Lưu ý |
|---|---|---|
| `JOIN FETCH` | Tải association trong query | Chú ý row multiplication và pagination |
| `@EntityGraph` | Khai báo fetch plan theo use case | Kiểm tra SQL provider thực thi |
| `@BatchSize` / batch fetch | Gom nhiều lazy loads thành batch | Giảm N+1 nhưng vẫn là truy vấn phát sinh khi truy cập |
| DTO projection | Chỉ truy vấn các cột cần xuất | Giảm entity/proxy và mapping dư thừa |
| Explicit initialization | Chủ động initialize association trong session | Có thể gây N+1 hoặc tải quá nhiều |

## 11. DTO projection để không tạo entity graph không cần thiết

Nếu endpoint chỉ cần một số field, có thể truy vấn thẳng DTO thay vì tải entity rồi chuyển đổi:

```java
public record OrderSummaryDto(
        Long id,
        String orderNumber,
        String customerName
) {
}
```

JPQL constructor projection:

```java
@Query("""
       select new com.example.api.OrderSummaryDto(
           o.id,
           o.orderNumber,
           c.name
       )
       from Order o
       join o.customer c
       where o.status = :status
       """)
List<OrderSummaryDto> findSummaries(@Param("status") OrderStatus status);
```

Query trả về DTO đã có dữ liệu cần thiết. Không cần tạo `Order` entity cùng proxy `customer` chỉ để Jackson lấy ba field. Với màn hình danh sách hoặc báo cáo, projection thường là lựa chọn hiệu quả và dễ kiểm soát.

## 12. Dùng Jackson Hibernate module khi thật sự cần serialize entity

Jackson có các module tích hợp với Hibernate để nhận diện proxy và persistent collection. Artifact cần chọn theo major version Hibernate đang dùng, ví dụ Hibernate 5, 6 hoặc 7. Tên module/package cụ thể phụ thuộc phiên bản tương ứng; không đăng ký module Hibernate 5 vào ứng dụng Hibernate 6 chỉ vì cả hai đều dùng Jackson.

Ví dụ với Hibernate 6:

```java
import com.fasterxml.jackson.datatype.hibernate6.Hibernate6Module;
import com.fasterxml.jackson.databind.ObjectMapper;

Hibernate6Module hibernateModule = new Hibernate6Module();

ObjectMapper mapper = new ObjectMapper()
        .registerModule(hibernateModule);
```

Với Hibernate 5 hoặc 7, dùng module tương ứng và version tương thích với Hibernate/Jackson của project. Nên để BOM quản lý các artifact Jackson cùng dòng phiên bản.

Hibernate module giúp Jackson xử lý proxy và collection của Hibernate theo các feature của module. Nó có thể tránh việc serialize trực tiếp các thuộc tính nội bộ của proxy hoặc chủ động điều khiển hành vi với association chưa initialize.

Tuy nhiên, module không thay thế fetch plan, DTO hoặc contract API. Nó không quyết định association nào nên được tải cho use case, cũng không làm cho mọi object graph an toàn để xuất.

### 12.1. Không ép lazy loading khi serialize

Một lựa chọn thường cần cân nhắc là không bật `FORCE_LAZY_LOADING`:

```java
Hibernate6Module hibernateModule = new Hibernate6Module();
hibernateModule.disable(Hibernate6Module.Feature.FORCE_LAZY_LOADING);
```

Khi không ép lazy loading, module tránh chủ động initialize proxy/collection chưa tải chỉ vì Jackson đang serialize. Kết quả biểu diễn cụ thể của association chưa initialize phụ thuộc feature khác, loại proxy/collection và phiên bản module. Có thể là null hoặc một biểu diễn identifier nếu đã bật tính năng tương ứng; hãy kiểm tra output của đúng phiên bản đang dùng.

Nếu bật `FORCE_LAZY_LOADING`, Jackson có thể khiến Hibernate truy vấn database khi serialize. Điều này có thể tái tạo N+1, tải graph quá lớn hoặc vẫn thất bại nếu session đã đóng. Chỉ bật khi ứng dụng thật sự chủ đích cho phép truy cập lazy trong giai đoạn serialize và đã kiểm soát transaction, truy vấn và payload.

### 12.2. Chỉ serialize identifier của proxy chưa initialize

Một số Hibernate module có feature `SERIALIZE_IDENTIFIER_FOR_LAZY_NOT_LOADED_OBJECTS`. Khi bật, proxy chưa initialize có thể được biểu diễn bằng object chỉ chứa identifier thay vì buộc tải entity:

```java
hibernateModule.enable(
        Hibernate6Module.Feature.SERIALIZE_IDENTIFIER_FOR_LAZY_NOT_LOADED_OBJECTS
);
```

Hình dạng JSON cụ thể phụ thuộc cấu hình wrap identifier và khả năng module xác định tên property ID. Đây không phải cách thay thế DTO: API có thể nhận một object chỉ có ID trong khi consumer mong đợi đầy đủ dữ liệu. Chỉ sử dụng nếu contract định nghĩa rõ association chưa tải được biểu diễn bằng identifier.

### 12.3. Các feature của Hibernate module cần được chọn có chủ đích

Các phiên bản module có thể cung cấp feature như:

- `FORCE_LAZY_LOADING`: có ép initialize proxy/collection chưa tải hay không.
- `SERIALIZE_IDENTIFIER_FOR_LAZY_NOT_LOADED_OBJECTS`: biểu diễn proxy chưa tải bằng identifier.
- `REPLACE_PERSISTENT_COLLECTIONS`: thay persistent collection bằng collection Java chuẩn trong một số trường hợp.
- `USE_TRANSIENT_ANNOTATION`: xử lý `@Transient` theo quy tắc của module.
- `REQUIRE_EXPLICIT_LAZY_LOADING_MARKER`: điều khiển nhận diện một số collection lazy theo metadata.

Tên và hành vi feature có thể khác giữa major version. Hãy xem Javadoc của đúng module/version được project sử dụng. Không bật tất cả feature theo mẫu trên mạng mà không hiểu output và ảnh hưởng đến API.

## 13. @JsonIgnore có thể ngăn Jackson đi vào association

Nếu một association không được phép xuất trong API, có thể bỏ nó khỏi serialization:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JsonIgnore
private Customer customer;
```

Hoặc đặt `@JsonIgnore` trên getter theo cách Jackson nhận diện property. Điều này có thể ngăn Jackson truy cập property đó và tránh lazy initialization từ đường serialize này.

Nhưng `@JsonIgnore` là chính sách JSON trên entity. Nó không thay thế DTO nếu mỗi endpoint cần một tập field khác nhau. Ngoài ra, cần xem xét tác động của annotation đến deserialize nếu entity được dùng làm input model. Với API public, dùng DTO riêng thường rõ ràng hơn việc gắn annotation theo từng endpoint lên entity persistence.

Không nên dùng `@JsonIgnore` một cách máy móc trên mọi quan hệ hai chiều mà không xác định contract. Có thể dùng DTO để tạo cấu trúc response không vòng lặp và chỉ xuất các field thực sự cần.

## 14. Vòng tham chiếu trong entity graph

Quan hệ hai chiều phổ biến trong ORM:

```java
@Entity
public class Order {
    @OneToMany(mappedBy = "order")
    private List<OrderItem> items;
}

@Entity
public class OrderItem {
    @ManyToOne
    private Order order;
}
```

Nếu Jackson serialize `Order`, nó đi vào `items`, sau đó từ mỗi `OrderItem` lại đi vào `order`, rồi quay lại danh sách `items`. Điều này có thể tạo vòng lặp vô hạn hoặc lỗi `JsonMappingException` về self-reference.

Jackson có `@JsonManagedReference` và `@JsonBackReference` cho một số mô hình quan hệ cha-con:

```java
public class Order {
    @JsonManagedReference
    private List<OrderItem> items;
}

public class OrderItem {
    @JsonBackReference
    private Order order;
}
```

`@JsonManagedReference` đánh dấu phía được serialize theo hướng cha đến con; `@JsonBackReference` đánh dấu phía ngược không được serialize như một property thông thường. Các annotation này có thể giải quyết một số vòng tham chiếu, nhưng không xử lý vấn đề lazy loading, N+1 hoặc việc xuất dữ liệu persistence không mong muốn.

`@JsonIdentityInfo` là lựa chọn khác khi contract muốn biểu diễn object identity và tham chiếu bằng ID. Tuy nhiên, nó làm thay đổi hình dạng JSON và consumer phải hiểu quy tắc identity. Với REST API thông thường, DTO phẳng hoặc DTO lồng nhau có cấu trúc rõ thường dễ dùng hơn.

## 15. Lazy LOB và tài nguyên JDBC đã đóng

Không chỉ association entity mới có thể tải chậm. Một số mapping có thể dùng lazy basic attribute hoặc large object (LOB), ví dụ `Blob`, `Clob`, `byte[]`, `String` lớn hoặc kiểu wrapper do provider quản lý.

Ví dụ:

```java
@Entity
public class Document {
    @Id
    private Long id;

    private String fileName;

    @Lob
    @Basic(fetch = FetchType.LAZY)
    private Blob content;
}
```

Một `Blob` có thể phụ thuộc vào connection hoặc tài nguyên JDBC mà provider đang quản lý. Nếu Jackson truy cập getter sau khi session/connection đã đóng, việc đọc nội dung có thể thất bại. Nếu serializer cố biến `Blob` hoặc wrapper thành một cấu trúc JSON không được thiết kế, output cũng có thể không phù hợp.

Lưu ý rằng `FetchType.LAZY` trên basic attribute là một yêu cầu/hint của JPA; khả năng trì hoãn tải field cơ bản như LOB phụ thuộc provider và cấu hình, và Hibernate thường cần bytecode enhancement để lazy-load basic attribute một cách hiệu quả. Hãy xác nhận mapping thực tế thay vì giả định annotation luôn bảo đảm field chưa được tải.

Các tài nguyên tương tự cần chú ý:

- `Blob` và `Clob`.
- `InputStream` hoặc `Reader` lấy từ JDBC/LOB.
- Stream từ file hoặc object storage.
- Cursor/iterator phụ thuộc transaction.
- Lazy basic field mà provider chỉ tải khi truy cập.

Đừng đưa trực tiếp handle tài nguyên vào DTO hoặc để Jackson tự quyết định cách serialize chúng. Hãy xác định API cần metadata, nội dung dạng byte/string hay một endpoint tải file riêng.

## 16. Chuyển LOB sang DTO khi tài nguyên còn mở

Nếu nội dung nhỏ và có giới hạn, có thể đọc dữ liệu trong transaction/resource scope rồi chuyển sang kiểu Java độc lập:

```java
@Transactional(readOnly = true)
public DocumentDto getDocument(Long id) throws SQLException, IOException {
    Document document = documentRepository.findById(id)
            .orElseThrow();

    Blob blob = document.getContent();
    byte[] content;

    try (InputStream input = blob.getBinaryStream()) {
        content = input.readAllBytes();
    }

    return new DocumentDto(
            document.getId(),
            document.getFileName(),
            content
    );
}
```

DTO:

```java
public record DocumentDto(
        Long id,
        String fileName,
        byte[] content
) {
}
```

Jackson có thể serialize `byte[]` theo quy tắc binary của Databind (thông thường là Base64 string trong JSON). Cần xác định rõ API muốn Base64 trong JSON hay muốn endpoint tải file với `application/octet-stream`.

Không dùng `readAllBytes()` cho LOB không giới hạn hoặc file rất lớn vì nó tạo một mảng byte lớn trong heap. Với dữ liệu lớn, hãy stream nội dung trực tiếp đến HTTP response hoặc object storage trong khi transaction/connection và stream nguồn còn mở, với cơ chế quản lý tài nguyên rõ ràng. Một endpoint tải file riêng thường phù hợp hơn nhúng file lớn vào JSON.

## 17. Không serialize Stream hoặc JDBC resource sau khi đóng

Một lỗi thiết kế là tạo DTO chứa `InputStream` rồi trả DTO ra ngoài transaction:

```java
public record UnsafeDocumentDto(
        Long id,
        InputStream content
) {
}
```

Nếu stream được lấy từ `Blob` trong transaction nhưng chỉ được Jackson đọc sau khi transaction kết thúc, stream có thể đã đóng hoặc connection không còn hợp lệ. Ngay cả khi stream còn mở, việc để serializer tự tiêu thụ stream làm cho vòng đời I/O phụ thuộc vào thời điểm Jackson ghi response.

Tốt hơn:

- Với dữ liệu nhỏ: đọc thành `byte[]` hoặc `String` trong resource scope rồi trả DTO.
- Với dữ liệu lớn: dùng endpoint streaming có chủ đích, nơi transaction và resource được giữ mở trong suốt quá trình copy, rồi đóng đúng cách.
- Với metadata: chỉ trả ID, tên file, content type, kích thước và URL tải riêng; không trả resource handle.

Không giữ `ResultSet`, `Blob`, `Clob`, `InputStream` hoặc JDBC connection trong object response chờ serialize.

## 18. Kiểm tra trạng thái lazy trước khi truy cập

Khi cần chẩn đoán hoặc có logic đặc biệt, Hibernate cung cấp `Hibernate.isInitialized(...)` để kiểm tra proxy/collection đã được initialize chưa:

```java
if (Hibernate.isInitialized(order.getItems())) {
    int count = order.getItems().size();
}
```

JPA có `PersistenceUnitUtil.isLoaded(...)` để kiểm tra trạng thái load theo entity/attribute:

```java
PersistenceUnitUtil util = entityManagerFactory
        .getPersistenceUnitUtil();

boolean itemsLoaded = util.isLoaded(order, "items");
```

Các phép kiểm tra này hữu ích cho diagnostic hoặc một số luồng xử lý có chủ đích. Chúng không tự tải dữ liệu và không thay thế fetch plan. Nếu code chỉ serialize khi property đã loaded, response có thể khác nhau tùy cách entity được truy vấn, dẫn đến API không ổn định.

Không gọi `Hibernate.initialize(...)` cho mọi association chỉ để tránh exception:

```java
Hibernate.initialize(order.getItems());
```

Lệnh này cần session còn mở và có thể tải toàn bộ collection. Nếu lặp qua nhiều order, nó có thể tạo N+1 queries. Chỉ initialize rõ ràng khi số lượng và phạm vi dữ liệu đã được kiểm soát; thường fetch join, EntityGraph hoặc DTO projection thể hiện ý định tốt hơn.

## 19. Kiểm tra SQL phát sinh trong lúc serialize

Để phát hiện lazy loading ẩn, cần quan sát SQL và số query ở một request thực tế hoặc integration test.

Các cách kiểm tra thường dùng:

- Bật SQL logging của Hibernate trong môi trường phát triển/test.
- Bật Hibernate statistics để quan sát số prepared statement và entity/collection fetch.
- Dùng datasource proxy hoặc APM để ghi nhận truy vấn theo request.
- Viết integration test kiểm tra query count cho endpoint có danh sách entity.
- Chụp query log trước và sau khi thay DTO/fetch plan.

Một bài test có thể tách hai giai đoạn:

1. Gọi service để lấy DTO trong transaction.
2. Serialize DTO sau khi transaction đã kết thúc.

Nếu serialization DTO vẫn cần truy vấn ORM, DTO có thể đang giữ entity/proxy hoặc stream thay vì giá trị độc lập. DTO nên chứa scalar, collection DTO hoặc các cấu trúc dữ liệu đã được materialize theo contract.

## 20. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `LazyInitializationException` trong lúc ghi JSON | Jackson gọi getter lazy sau khi session đóng | Fetch dữ liệu và map DTO trong transaction |
| Serialize chậm bất thường | Getter kích hoạt nhiều truy vấn | Kiểm tra SQL, dùng fetch plan/projection |
| N+1 queries | Serialize từng entity làm initialize association riêng | Fetch join, EntityGraph, batch fetching hoặc DTO query |
| JSON chứa quá nhiều dữ liệu | Jackson đi sâu vào toàn bộ entity graph | DTO allowlist field theo endpoint |
| Vòng lặp serialize | Quan hệ hai chiều parent/child | DTO, managed/back reference hoặc identity theo contract |
| Proxy được ghi thành object lạ | Jackson không xử lý Hibernate proxy phù hợp | Dùng DTO hoặc Hibernate module tương thích |
| Association chưa tải thành null/ID | Cấu hình Hibernate module không ép lazy load | Xác định output contract; tải dữ liệu cần thiết trước khi serialize |
| Lỗi khi đọc LOB | Blob/Clob/stream phụ thuộc connection đã đóng | Materialize có giới hạn hoặc stream trong resource scope |
| Output thay đổi theo OSIV/session | Lazy property được tải tùy thời điểm serialize | Không phụ thuộc OSIV; kiểm soát fetch plan và DTO |

## 21. Quy trình thiết kế response có dữ liệu ORM tải chậm

Khi endpoint cần trả dữ liệu từ entity có association lazy, hãy đi theo các bước:

1. Xác định chính xác field nào thuộc JSON contract của endpoint.
2. Kiểm tra field nào là scalar đã tải, proxy, persistent collection, lazy basic field hoặc LOB.
3. Chọn fetch plan theo use case: DTO projection, fetch join, EntityGraph hoặc batch fetch.
4. Tải và ánh xạ dữ liệu sang DTO trong transaction/persistence context còn mở.
5. Không đưa entity, proxy, `PersistentCollection`, `Blob`, `Clob` hoặc stream phụ thuộc JDBC vào DTO response.
6. Nếu cần file lớn, dùng endpoint streaming riêng với vòng đời transaction/resource rõ ràng.
7. Serialize DTO sau khi persistence context có thể đã đóng.
8. Quan sát SQL/query count để bảo đảm serialization không kích hoạt truy vấn ORM.
9. Test trường hợp association rỗng, association chưa được yêu cầu, session đóng và LOB đã đóng.

Nếu hệ thống có lý do phải serialize entity trực tiếp, hãy xác định rõ Hibernate module tương thích, feature lazy loading, vòng tham chiếu, fetch plan và output của association chưa initialize. Cần test với đúng phiên bản Hibernate/Jackson và không xem module là cách thay thế thiết kế API.

## 22. Ghi nhớ

Entity ORM có thể chứa proxy, persistent collection và lazy attribute chỉ tải được khi persistence context còn mở. Jackson gọi getter trong lúc serialize nên có thể kích hoạt SQL, gây N+1 hoặc ném `LazyInitializationException` khi entity đã detached. OSIV có thể làm lỗi biến mất nhưng vẫn để truy vấn phát sinh trong giai đoạn ghi response.

Hãy ưu tiên truy vấn theo fetch plan rõ ràng và ánh xạ sang DTO trong transaction. Dùng fetch join, EntityGraph, DTO projection hoặc batch fetching theo đúng use case; kiểm tra SQL thực tế. Jackson Hibernate module có thể hỗ trợ proxy/collection nhưng cần chọn đúng major version và feature, đồng thời không thay thế DTO hay kiểm soát dữ liệu API.

Với LOB và tài nguyên JDBC, không để Jackson đọc `Blob`, `Clob`, `InputStream` hoặc cursor sau khi connection/session đóng. Materialize dữ liệu nhỏ trong resource scope, stream dữ liệu lớn bằng endpoint riêng, và không đưa resource handle vào object chờ serialize.

# Tránh vòng lặp, tải lười và lộ dữ liệu khi tuần tự hóa Entity

## 1. Vì sao trả Entity trực tiếp ra JSON dễ gặp vấn đề?

Trong ứng dụng Spring Data JPA, Entity mô tả dữ liệu và quan hệ trong persistence context. Jackson lại xem object mà controller trả về như một object graph cần duyệt để tạo JSON. Hai mô hình này có mục tiêu khác nhau: Entity có thể chứa quan hệ hai chiều, proxy LAZY và nhiều thuộc tính nội bộ; JSON response cần có cấu trúc hữu hạn, ổn định và chỉ chứa dữ liệu API được phép công khai.

Trả Entity trực tiếp từ REST controller có thể dẫn đến ba nhóm lỗi:

- **Vòng lặp tuần tự hóa:** Entity cha tham chiếu Entity con, Entity con lại tham chiếu cha, khiến Jackson duyệt qua lại hoặc báo lỗi self-reference.
- **Tải dữ liệu ngoài ý muốn:** Jackson gọi getter của association LAZY, làm Hibernate chạy SQL khi tạo response; sau khi persistence context đóng, có thể gặp `LazyInitializationException`.
- **Lộ dữ liệu:** Entity có thể chứa password hash, token, ghi chú nội bộ, tenant ID hoặc trường chưa từng được dự định đưa vào API.

Cách thiết kế an toàn là xem JSON response như một hợp đồng riêng và ánh xạ Entity sang DTO trong service khi dữ liệu cần thiết vẫn được tải trong transaction.

## 2. Vòng lặp trong quan hệ hai chiều

Ví dụ một khách hàng có nhiều đơn hàng, mỗi đơn hàng tham chiếu ngược về khách hàng:

```java
@Entity
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    private List<PurchaseOrder> orders = new ArrayList<>();
}
```

```java
@Entity
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private BigDecimal totalAmount;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;
}
```

Nếu controller trả một `Customer`, Jackson có thể duyệt object graph như sau:

```text
Customer
  -> orders
       -> PurchaseOrder
            -> customer
                 -> orders
                      -> PurchaseOrder
                           -> customer
                                -> ...
```

Quan hệ JPA vẫn đúng về mặt database, nhưng object graph không có điểm dừng tự nhiên cho quá trình chuyển thành JSON. Kết quả có thể là lỗi kiểu `Infinite recursion` hoặc `JsonMappingException`, response rất lớn, hay stack overflow.

Vòng lặp không chỉ xảy ra với OneToMany/ManyToOne. ManyToMany, association lồng nhiều tầng hoặc hai object cùng tham chiếu lẫn nhau cũng có thể tạo chu trình.

## 3. Giải pháp ưu tiên: DTO response

DTO xác định rõ trường nào được trả về và dừng việc serialize tại cấu trúc mà API mong muốn. Ví dụ:

```java
public record OrderSummaryResponse(
    Long id,
    BigDecimal totalAmount
) {
}

public record CustomerResponse(
    Long id,
    String name,
    List<OrderSummaryResponse> orders
) {
}
```

Service tải association cần thiết rồi map sang DTO trong transaction:

```java
@Service
public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public CustomerResponse getCustomer(Long id) {
        Customer customer = repository.findDetailedById(id)
            .orElseThrow(() -> new EntityNotFoundException("Customer not found"));

        List<OrderSummaryResponse> orders = customer.getOrders().stream()
            .map(order -> new OrderSummaryResponse(
                order.getId(),
                order.getTotalAmount()
            ))
            .toList();

        return new CustomerResponse(
            customer.getId(),
            customer.getName(),
            orders
        );
    }
}
```

Repository khai báo fetch plan cho đúng use case:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    @EntityGraph(attributePaths = "orders")
    @Query("select c from Customer c where c.id = :id")
    Optional<Customer> findDetailedById(@Param("id") Long id);
}
```

Ví dụ cần import `EntityGraph`, `Query`, `Param`, `Optional` và các kiểu domain tương ứng. Có thể dùng `JOIN FETCH` thay cho EntityGraph nếu query cần điều kiện hoặc fetch plan tường minh. Mapping sang DTO diễn ra trước khi transaction kết thúc nên response không cần Jackson truy cập association LAZY.

DTO cũng tạo ranh giới API ổn định: Entity có thể được bổ sung field hoặc association mà JSON response không tự động thay đổi. Với danh sách lớn, cân nhắc DTO projection trực tiếp từ query để chỉ đọc các cột cần thiết.

## 4. Dùng DTO cho cả request và response

Không nên nhận JSON request rồi bind trực tiếp vào Entity. Nếu client gửi thêm field như `role`, `tenantId`, `createdBy` hoặc `passwordHash`, việc bind Entity trực tiếp có thể tạo mass-assignment vulnerability hoặc làm thay đổi trạng thái không được phép.

Thay vào đó, định nghĩa request DTO chỉ có các trường mà client được phép gửi:

```java
public record UpdateCustomerRequest(
    @NotBlank
    @Size(max = 100)
    String name
) {
}
```

Service lấy Entity hiện tại, kiểm tra quyền và cập nhật các field được cho phép:

```java
@Transactional
public void updateCustomer(Long id, UpdateCustomerRequest request) {
    Customer customer = repository.findById(id)
        .orElseThrow(() -> new EntityNotFoundException("Customer not found"));

    // Kiểm tra người gọi có quyền cập nhật customer này.
    customer.setName(request.name());
}
```

Đoạn code là minh họa; cần triển khai kiểm tra quyền theo security model của ứng dụng. Request DTO và response DTO có thể khác nhau vì dữ liệu client được phép gửi không nhất thiết giống dữ liệu server được phép trả.

## 5. @JsonManagedReference và @JsonBackReference

Nếu cần giữ Entity làm cấu trúc JSON trong một trường hợp nhỏ, Jackson cung cấp cặp annotation để định nghĩa chiều serialize của quan hệ hai chiều:

```java
@Entity
public class Customer {
    @Id
    private Long id;

    @JsonManagedReference
    @OneToMany(mappedBy = "customer")
    private List<PurchaseOrder> orders = new ArrayList<>();
}

@Entity
public class PurchaseOrder {
    @Id
    private Long id;

    @JsonBackReference
    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;
}
```

`@JsonManagedReference` đánh dấu phía được serialize bình thường; `@JsonBackReference` đánh dấu phía ngược không được serialize trong cặp đó. Điều này ngăn Jackson đi ngược từ order về customer trong quá trình tạo JSON.

Nếu một class có nhiều quan hệ hai chiều, đặt tên cặp reference riêng bằng thuộc tính `value`, ví dụ `@JsonManagedReference("customer-orders")` và `@JsonBackReference("customer-orders")`, để tránh nhập nhằng.

Giới hạn: cách này gắn cấu trúc JSON vào Entity và chỉ xử lý chiều tham chiếu của cặp được đánh dấu. Nó không giải quyết việc tải LAZY, không giới hạn các field nhạy cảm khác và không thay thế DTO cho API có nhiều loại response. Hành vi deserialize cũng có quy tắc riêng; hãy kiểm thử nếu dùng Entity làm request body.

## 6. @JsonIgnore

`@JsonIgnore` có thể bỏ một thuộc tính khỏi quá trình serialize:

```java
@Entity
public class PurchaseOrder {
    @Id
    private Long id;

    @JsonIgnore
    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;
}
```

Trong ví dụ này, Jackson không đi từ PurchaseOrder ngược về Customer khi tạo JSON, nhờ đó có thể ngắt một chu trình đơn giản.

Nhưng `@JsonIgnore` có tác động tới hợp đồng JSON và thường ảnh hưởng cả deserialize property. Nếu API cần cho phép ghi nhưng không cho đọc, hoặc ngược lại, hãy xem các tùy chọn Jackson như `@JsonProperty(access = ...)` và kiểm thử rõ ràng. Không dùng annotation này như cơ chế authorization: field vẫn có thể bị lộ qua endpoint, DTO hoặc query khác.

Đừng gắn `@JsonIgnore` một cách rải rác chỉ để sửa từng lỗi recursion. Khi quan hệ và response phát triển, DTO thường dễ kiểm soát hơn.

## 7. @JsonIdentityInfo

Jackson có thể biểu diễn object identity để những lần tham chiếu lặp lại dùng ID thay vì serialize lại toàn bộ object:

```java
@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id"
)
@Entity
public class Customer {
    @Id
    private Long id;

    @OneToMany(mappedBy = "customer")
    private List<PurchaseOrder> orders = new ArrayList<>();
}
```

Khi object đã được serialize, lần tham chiếu sau có thể được biểu diễn bằng object ID. Cách này xử lý tham chiếu lặp theo identity, nhưng JSON output có thể chứa ID reference thay vì một object lồng đầy đủ. Client phải hiểu và giải quyết các reference đó.

`@JsonIdentityInfo` không ngăn lazy loading, không tự chọn association nào cần tải và không loại field nhạy cảm. Chỉ dùng khi API thực sự muốn mô hình JSON có object identity và consumer có thể xử lý định dạng đó.

## 8. Vì sao LAZY có thể gây lỗi khi Jackson serialize?

Với `FetchType.LAZY`, Hibernate thường giữ association dưới dạng proxy hoặc persistent collection chưa được tải. Jackson đọc property bằng getter để tạo JSON. Việc gọi getter có thể kích hoạt truy vấn:

```text
Controller trả Customer Entity
        |
        v
Jackson gọi getOrders()
        |
        v
Hibernate khởi tạo collection LAZY
        |
        v
SQL chạy trong lúc tạo JSON
```

Nếu persistence context vẫn mở, SQL có thể chạy thành công. Nếu session đã đóng, Hibernate có thể ném `LazyInitializationException` vì không thể khởi tạo association chưa được tải.

Đây là lý do response JSON không nên quyết định fetch plan một cách ngẫu nhiên thông qua getter. Service/repository cần xác định dữ liệu cần thiết trước khi controller serialize.

## 9. Open Session In View và N+1

Spring Boot có thể giữ EntityManager mở trong suốt quá trình xử lý web request bằng Open EntityManager in View (OSIV). Cấu hình thường gặp để tắt OSIV:

```yaml
spring:
  jpa:
    open-in-view: false
```

Khi OSIV bật, Jackson có thể truy cập association LAZY sau khi service method kết thúc và kích hoạt thêm SQL. Điều này đôi khi che giấu việc service chưa tải đủ dữ liệu. Một response chứa 30 đơn hàng và mỗi đơn hàng truy cập customer có thể gây N+1 query ngay trong quá trình serialize.

Tắt OSIV giúp phát hiện sớm các association chưa được tải ngoài transaction, nhưng không tự sửa fetch plan. Service vẫn phải tải dữ liệu cần thiết và map DTO trong transaction. Một số hệ thống chọn bật OSIV có chủ đích; dù vậy, không nên dựa vào nó để điều khiển dữ liệu trả về hoặc bỏ qua việc đo N+1.

Không đổi mọi association sang EAGER để tránh `LazyInitializationException`. EAGER có thể tải quá nhiều dữ liệu, gây nhiều query phụ và tạo N+1 ở một đường truy cập khác. Dùng fetch plan cụ thể cho từng use case.

## 10. Hibernate Jackson module

Jackson có module tích hợp với Hibernate để xử lý một số kiểu proxy và persistent collection. Artifact/module phải khớp major version Hibernate, ví dụ Hibernate 6 dùng module tương ứng Hibernate 6; dự án Hibernate 7 cần module tương ứng phiên bản đó.

Đăng ký module theo cấu hình Jackson của ứng dụng, ví dụ với Hibernate 6:

```java
@Configuration
public class JacksonConfiguration {
    @Bean
    public Module hibernateModule() {
        return new Hibernate6Module();
    }
}
```

Ví dụ cần dependency `jackson-datatype-hibernate6` tương thích với Jackson/Hibernate trong dự án và import `com.fasterxml.jackson.datatype.hibernate6.Hibernate6Module`. Nếu Spring Boot đã tự cấu hình module hoặc ứng dụng có ObjectMapper riêng, tránh đăng ký trùng.

Module có thể kiểm soát cách proxy và collection LAZY được serialize; kết quả cụ thể phụ thuộc module, feature flags và cấu hình. Một số tùy chọn có thể buộc tải lazy data hoặc serialize identifier của proxy chưa khởi tạo. Không bật force-loading nếu không muốn Jackson tự kích hoạt query.

Module không thay thế fetch plan, DTO hay kiểm soát field nhạy cảm. Hãy kiểm tra JSON thực tế và số SQL phát sinh khi bật từng feature.

## 11. Tránh proxy metadata lọt vào JSON

Trong một số cấu hình, proxy Hibernate có các thuộc tính kỹ thuật như `hibernateLazyInitializer` và `handler`. Nếu Entity bị serialize trực tiếp, Jackson có thể gặp lỗi hoặc nhìn thấy các thuộc tính không thuộc API.

Annotation sau đôi khi được dùng để bỏ qua proxy metadata:

```java
@JsonIgnoreProperties({"hibernateLazyInitializer", "handler"})
@Entity
public class Customer {
    // Entity fields
}
```

Đây chỉ là biện pháp tương thích cho một số trường hợp proxy. Nó không ngăn recursion giữa Entity, không bảo đảm association LAZY không chạy SQL và không bảo vệ các field nghiệp vụ nhạy cảm. DTO vẫn là lựa chọn rõ ràng hơn.

## 12. Cẩn thận với Lombok toString, equals và hashCode

`@Data` của Lombok sinh getter, setter, `toString()`, `equals()` và `hashCode()` dựa trên các field. Nếu Entity có association hai chiều, các method sinh tự động có thể:

- Gọi `toString()` đệ quy qua parent và child.
- Gọi getter association LAZY và kích hoạt SQL ngoài dự kiến.
- Làm `equals()`/`hashCode()` thay đổi khi collection hoặc ID thay đổi.
- Tạo recursion khi hai Entity so sánh hoặc log nhau.

Với Entity JPA, thường nên dùng `@Getter`/`@Setter` có chọn lọc và tự kiểm soát `equals`, `hashCode`, `toString`. Không đưa collection/association vào `toString()` hoặc equality một cách máy móc. Nếu dùng ID làm định danh, phải cân nhắc thời điểm ID được sinh và quy tắc equality của Entity mới/chưa persist.

Ví dụ Lombok có thể loại association khỏi `toString`:

```java
@Getter
@Setter
@ToString(exclude = {"customer", "items"})
@Entity
public class PurchaseOrder {
    // fields and mappings
}
```

Đoạn trên chỉ minh họa cách loại field khỏi toString; vẫn cần thiết kế equals/hashCode riêng và không dùng annotation này để xử lý JSON serialization.

## 13. Lộ dữ liệu khi serialize Entity

Entity thường chứa nhiều dữ liệu hơn API response cần. Ví dụ:

```java
@Entity
public class UserAccount {
    @Id
    private Long id;

    private String email;
    private String passwordHash;
    private String resetToken;
    private String internalNote;
    private String role;
}
```

Nếu controller trả `UserAccount` trực tiếp, những field có getter có thể được Jackson đưa vào JSON theo cấu hình mặc định. Việc thêm một field mới vào Entity trong tương lai cũng có thể vô tình thay đổi response.

Response DTO tạo allow-list dữ liệu:

```java
public record UserAccountResponse(
    Long id,
    String email
) {
}
```

Không đưa password hash, reset token, API key, secret, nội dung nội bộ, thông tin tenant hoặc field chỉ dành cho quản trị vào DTO công khai. Dùng DTO riêng cho từng quyền hoặc use case khi cần. Việc kiểm tra authorization phải diễn ra ở server trước khi tạo response; ẩn field bằng Jackson không thay thế kiểm tra quyền.

## 14. Không serialize Entity graph hai chiều trực tiếp

Ngay cả khi đã dùng `@JsonManagedReference`, `@JsonBackReference` hoặc `@JsonIdentityInfo`, response vẫn phụ thuộc vào cấu trúc persistence model. Thay đổi quan hệ có thể làm thay đổi JSON, tăng payload hoặc tạo truy vấn mới trong lúc serialize.

Một cách tổ chức thường dễ bảo trì:

```text
Controller
   | nhận request DTO
   v
Service (@Transactional)
   | gọi repository với fetch plan phù hợp
   | map Entity -> response DTO
   v
Controller trả response DTO
   |
   v
Jackson serialize DTO không chứa proxy Entity
```

DTO nên chứa scalar hoặc DTO lồng nhau có cấu trúc hữu hạn. Nếu cần biểu diễn quan hệ cha-con, chỉ chọn một chiều lồng object; phía ngược có thể là ID hoặc không xuất hiện.

## 15. Kiểm thử JSON và truy vấn

Integration test nên kiểm tra cả cấu trúc response lẫn hành vi persistence:

1. Gọi endpoint có quan hệ hai chiều và xác nhận response không bị recursion.
2. Xác nhận chỉ các field được phép xuất hiện; password hash, token và internal note không có trong JSON.
3. Kiểm tra association cần thiết được tải trong transaction trước khi mapping DTO.
4. Tắt OSIV trong test hoặc cấu hình tương tự production để phát hiện truy cập LAZY sau transaction.
5. Đếm SQL khi serialize danh sách nhiều Entity để phát hiện N+1.
6. Kiểm tra response không thay đổi ngoài ý muốn khi thêm field mới vào Entity.
7. Kiểm tra trường hợp collection rỗng, association null và Entity không tồn tại.
8. Kiểm tra request DTO không cho client cập nhật field server-managed.

Ví dụ assertion với MockMvc:

```java
mockMvc.perform(get("/users/{id}", id))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.email").value("user@example.com"))
    .andExpect(jsonPath("$.passwordHash").doesNotExist())
    .andExpect(jsonPath("$.resetToken").doesNotExist());
```

Test này xác nhận response không chứa các field nhạy cảm. Cần bổ sung test số lượng query hoặc quan sát SQL riêng để phát hiện N+1; JSON assertion không tự kiểm tra hiệu năng.

## 16. Lỗi thường gặp và cách xử lý

**Infinite recursion hoặc stack overflow.** Tìm quan hệ hai chiều trong object graph. Ưu tiên DTO; nếu cần quick fix cho một cặp reference, cân nhắc `@JsonManagedReference`/`@JsonBackReference`.

**LazyInitializationException khi serialize.** Service trả Entity có association chưa tải sau khi transaction đóng. Tải dữ liệu bằng fetch join/EntityGraph và map DTO trong transaction.

**Response chạy nhiều SQL dù controller chỉ gọi một repository method.** Jackson đang truy cập getter LAZY trong lúc serialize hoặc mapping. Xem SQL log và fetch plan; không dựa vào OSIV để che giấu N+1.

**JSON chứa proxy metadata.** Kiểm tra Hibernate Jackson module hoặc `@JsonIgnoreProperties` cho proxy metadata; sau đó cân nhắc chuyển sang DTO.

**Response lộ field mới sau khi Entity được mở rộng.** Không trả Entity trực tiếp. Dùng DTO allow-list và test JSON.

**Ẩn association bằng `@JsonIgnore` nhưng request không cập nhật được field.** Kiểm tra semantics serialize/deserialize của annotation; dùng request DTO riêng thay vì tái sử dụng Entity.

**Lombok toString gây recursion hoặc query phụ.** Loại association khỏi toString và viết equals/hashCode phù hợp với lifecycle Entity.

**EAGER làm response chậm hơn.** Trả về mapping LAZY có kiểm soát và định nghĩa fetch plan riêng theo use case.

## 17. Checklist thiết kế API với JPA

- Không trả Entity trực tiếp nếu response có quan hệ, field nội bộ hoặc cấu trúc thay đổi theo persistence model.
- Tạo request DTO và response DTO riêng.
- Tải association cần thiết bằng JOIN FETCH, EntityGraph hoặc batch fetching trong service transaction.
- Map Entity sang DTO trước khi transaction kết thúc.
- Không dùng EAGER toàn cục để sửa lỗi lazy loading.
- Dùng Jackson reference annotations chỉ khi cấu trúc JSON thực sự phù hợp; chúng không giải quyết N+1 hay authorization.
- Dùng Hibernate Jackson module đúng major version nếu có lý do cần serialize proxy; kiểm tra feature flags và SQL.
- Không coi `@JsonIgnore` là ranh giới bảo mật.
- Tránh `@Data` trên Entity có quan hệ; kiểm soát toString/equals/hashCode.
- Tắt hoặc đánh giá kỹ OSIV; test theo cấu hình production.
- Kiểm thử recursion, lazy loading, số SQL và field nhạy cảm trong JSON.

JPA Entity mô tả mô hình lưu trữ và quan hệ; JSON DTO mô tả dữ liệu API được phép trao đổi. Giữ hai mô hình riêng, tải association theo use case và map trong transaction giúp tránh vòng lặp, query LAZY ngoài dự kiến và rò rỉ dữ liệu.
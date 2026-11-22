# Phân tách Entity lưu trữ với DTO và mô hình phản hồi

Trong ứng dụng Spring Data JPA, Entity mô tả dữ liệu được persistence layer quản lý, còn DTO (Data Transfer Object) mô tả dữ liệu đi qua ranh giới giữa các tầng hoặc giữa API và client. Hai mô hình có mục đích khác nhau nên không nên dùng Entity làm request body hoặc response JSON cho mọi endpoint.

Tách Entity khỏi DTO giúp kiểm soát dữ liệu đầu vào/đầu ra, tránh để client sửa trực tiếp các trường nội bộ, giảm phụ thuộc API vào schema database và hạn chế lỗi do lazy loading hoặc vòng lặp serialize quan hệ. Đổi lại, ứng dụng cần có mapping rõ ràng và chọn thời điểm tải dữ liệu phù hợp.

Một thiết kế thường gặp là: Controller nhận request DTO, Service xác thực quy tắc nghiệp vụ và điều phối transaction, Repository đọc/ghi Entity, Mapper chuyển Entity thành response DTO. Với truy vấn danh sách hoặc màn hình chỉ cần một số trường, projection có thể lấy dữ liệu trực tiếp theo cấu trúc đầu ra.

## 1. Entity, DTO và response model khác nhau thế nào?

| Mô hình | Mục đích | Ví dụ |
|---|---|---|
| JPA Entity | Đại diện trạng thái được persistence provider quản lý và ánh xạ xuống bảng | Customer, PurchaseOrder |
| Request DTO | Mô tả dữ liệu client được phép gửi vào một thao tác | CreateCustomerRequest |
| Command | Mô tả ý định nghiệp vụ mà service cần thực hiện | CreateCustomerCommand |
| Response DTO | Mô tả dữ liệu endpoint được phép trả về | CustomerResponse |
| Projection | Chỉ lấy một tập thuộc tính cần cho truy vấn đọc | CustomerSummary |
| Domain model | Mô hình quy tắc và hành vi nghiệp vụ; có thể trùng hoặc tách khỏi Entity tùy kiến trúc | Customer aggregate |

DTO không nhất thiết phải là class riêng cho mọi trường hợp, nhưng request và response thường có yêu cầu khác nhau. Ví dụ khi tạo khách hàng, client gửi password thô; server lưu password hash; response tuyệt đối không trả password hoặc hash.

Entity có thể chứa khóa chính, version, quan hệ JPA, trường nội bộ phục vụ persistence, trạng thái nghiệp vụ và dữ liệu nhạy cảm. Response model chỉ nên chứa thông tin mà API chủ động công bố. Không để việc thêm một field vào Entity tự động làm field đó xuất hiện trong JSON.

## 2. Vì sao không nên trả Entity trực tiếp từ Controller?

Trả Entity trực tiếp có thể tạo ra nhiều vấn đề:

1. **Lộ dữ liệu nội bộ:** Entity có thể chứa passwordHash, internalNote, trạng thái kiểm duyệt hoặc thông tin không được phép công bố.
2. **API phụ thuộc schema:** thay đổi mapping hoặc đổi tên thuộc tính Entity có thể làm thay đổi JSON contract.
3. **Lazy loading:** serializer truy cập quan hệ LAZY sau khi transaction kết thúc và gây LazyInitializationException.
4. **N+1 query:** serializer duyệt một collection và kích hoạt thêm truy vấn cho từng Entity.
5. **Vòng lặp quan hệ:** Customer có orders, mỗi Order lại có customer; Jackson có thể lặp vô hạn hoặc cần annotation đặc biệt.
6. **Mass assignment:** client gửi thêm thuộc tính Entity như role, status, ownerId hoặc version và vô tình sửa dữ liệu ngoài ý muốn.
7. **Khó version API:** một Entity thường được nhiều use case sử dụng, trong khi mỗi endpoint cần hình dạng dữ liệu khác nhau.

Ví dụ không nên:

~~~java
@PostMapping("/customers")
public Customer create(@RequestBody Customer customer) {
    return customerRepository.save(customer);
}
~~~

Client có thể gửi nhiều field hơn yêu cầu nghiệp vụ. Entity được bind trực tiếp từ JSON cũng khiến Controller gắn chặt với persistence model.

Cách an toàn hơn là nhận request DTO, gọi service và trả response DTO.

## 3. Thiết kế Entity cho persistence layer

Ví dụ Entity Customer có dữ liệu nội bộ:

~~~java
import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, unique = true, length = 254)
    private String email;

    @Column(name = "password_hash", nullable = false)
    private String passwordHash;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private CustomerStatus status;

    @Version
    private Long version;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected Customer() {
    }

    public Customer(String name, String email, String passwordHash) {
        this.name = name;
        this.email = email;
        this.passwordHash = passwordHash;
        this.status = CustomerStatus.PENDING;
    }

    public void rename(String name) {
        this.name = name;
    }

    public void changeEmail(String email) {
        this.email = email;
    }

    public void activate() {
        this.status = CustomerStatus.ACTIVE;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    public String getPasswordHash() {
        return passwordHash;
    }

    public CustomerStatus getStatus() {
        return status;
    }

    public Long getVersion() {
        return version;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

Enum:

~~~java
public enum CustomerStatus {
    PENDING,
    ACTIVE,
    SUSPENDED
}
~~~

Đây là ví dụ Entity minh họa; constructor, getter và mapping cần được điều chỉnh theo dự án. Điểm đáng chú ý:
- passwordHash là dữ liệu persistence nội bộ.
- status được khởi tạo theo quy tắc nghiệp vụ, không nhận tùy ý từ request tạo mới.
- version hỗ trợ optimistic locking.
- Entity cung cấp phương thức nghiệp vụ thay vì để Controller gán trực tiếp mọi field.
- Entity có constructor mặc định protected theo yêu cầu của JPA.

Không cần tạo setter công khai cho mọi field. Giới hạn điểm thay đổi giúp bảo vệ invariant và tránh việc tầng web sửa trực tiếp các trường persistence.

## 4. Request DTO cho thao tác tạo mới

Request DTO chỉ chứa dữ liệu client được phép cung cấp:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateCustomerRequest(
        @NotBlank
        @Size(max = 120)
        String name,

        @NotBlank
        @Email
        @Size(max = 254)
        String email,

        @NotBlank
        @Size(min = 12, max = 128)
        String password
) {
}
~~~

Các annotation validation giúp kiểm tra hình thức dữ liệu đầu vào:
- NotBlank từ chối null, chuỗi rỗng và chuỗi chỉ có khoảng trắng.
- Email kiểm tra định dạng email ở mức validation.
- Size giới hạn độ dài.
- Quy tắc password ở đây chỉ là ví dụ; ứng dụng cần chính sách mật khẩu phù hợp.

Validation DTO không thay thế validation nghiệp vụ. Ví dụ email đã tồn tại cần được kiểm tra ở service/database. Unique constraint trong database vẫn cần thiết vì hai request đồng thời có thể cùng vượt qua bước kiểm tra trước khi ghi.

Request DTO không có id, passwordHash, status, createdAt hoặc version. Client không thể gửi các field đó để ép Entity nhận giá trị ngoài ý muốn.

## 5. Response DTO cho dữ liệu công khai

Response DTO mô tả chính xác những gì endpoint được phép trả:

~~~java
import java.time.Instant;

public record CustomerResponse(
        Long id,
        String name,
        String email,
        CustomerStatus status,
        Instant createdAt,
        Long version
) {
}
~~~

Response không chứa password hoặc passwordHash. Có thể đưa version ra response nếu client cần gửi lại version trong lần cập nhật để phát hiện dữ liệu cũ; nếu không, có thể giữ version ở header ETag hoặc không công khai.

Một API khác có thể cần response khác:
- CustomerSummary cho danh sách.
- CustomerDetailResponse cho trang chi tiết.
- CustomerAdminResponse cho màn hình quản trị.
- CustomerPublicProfile cho endpoint công khai.

Không nên tạo một response DTO quá lớn rồi trả ở mọi endpoint. Hãy chọn dữ liệu theo use case và quyền truy cập.

## 6. Tạo Entity từ request qua Service

Không nên để Controller tự tạo Entity rồi gọi Repository. Service là nơi kiểm tra quy tắc nghiệp vụ và phối hợp việc ghi.

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;
    private final PasswordEncoder passwordEncoder;
    private final CustomerMapper mapper;

    public CustomerService(
            CustomerRepository repository,
            PasswordEncoder passwordEncoder,
            CustomerMapper mapper) {
        this.repository = repository;
        this.passwordEncoder = passwordEncoder;
        this.mapper = mapper;
    }

    @Transactional
    public CustomerResponse create(CreateCustomerRequest request) {
        if (repository.existsByEmailIgnoreCase(request.email())) {
            throw new DuplicateCustomerEmailException(request.email());
        }

        String passwordHash =
                passwordEncoder.encode(request.password());

        Customer customer = new Customer(
                request.name().trim(),
                request.email().trim().toLowerCase(Locale.ROOT),
                passwordHash
        );

        Customer saved = repository.save(customer);

        return mapper.toResponse(saved);
    }
}
~~~

Ví dụ cần có PasswordEncoder bean, Repository, Mapper và exception tương ứng. Nếu database có collation hoặc quy tắc chuẩn hóa email riêng, hãy thống nhất normalization giữa validation, truy vấn và unique constraint.

Service chịu trách nhiệm:
1. Kiểm tra điều kiện nghiệp vụ.
2. Hash password bằng PasswordEncoder.
3. Tạo Entity theo trạng thái hợp lệ.
4. Lưu Entity trong transaction.
5. Chuyển kết quả thành response DTO.

Không bao giờ lưu password thô. Không trả hash trong response hoặc log.

## 7. Controller chỉ làm nhiệm vụ HTTP

Controller nhận request DTO, kích hoạt validation, gọi service và trả response DTO:

~~~java
@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<CustomerResponse> create(
            @Valid @RequestBody CreateCustomerRequest request) {

        CustomerResponse response = service.create(request);

        URI location = URI.create("/api/customers/" + response.id());

        return ResponseEntity.created(location).body(response);
    }
}
~~~

Controller không nên tự gọi EntityManager, tự quyết định persist hay merge, tự hash password, trả Entity, chứa logic cập nhật nhiều Repository hoặc xử lý lazy relationship bằng cách gọi getter tùy tiện.

Các exception nghiệp vụ có thể được ánh xạ sang HTTP status qua @RestControllerAdvice. Không trả stack trace hoặc chi tiết database cho client.

## 8. Mapper có vai trò gì?

Mapper chuyển đổi giữa các mô hình. Nó có thể là phương thức Java viết thủ công, MapStruct sinh code lúc biên dịch, một assembler riêng theo use case hoặc constructor projection trực tiếp từ query cho đường đọc.

Mapper không nên trở thành nơi chứa quy tắc nghiệp vụ quan trọng. Ví dụ chọn trạng thái ACTIVE, xác minh email, hash password hoặc kiểm tra quyền phải thuộc service/domain/security layer.

Mapper thường phù hợp với các phép chuyển đổi cấu trúc:
- Customer Entity sang CustomerResponse.
- Address Entity sang AddressResponse.
- Request DTO sang command.
- Projection sang response model.

## 9. Mapping thủ công

Với response DTO đơn giản, mapper thủ công rất rõ ràng:

~~~java
@Component
public class CustomerMapper {

    public CustomerResponse toResponse(Customer customer) {
        return new CustomerResponse(
                customer.getId(),
                customer.getName(),
                customer.getEmail(),
                customer.getStatus(),
                customer.getCreatedAt(),
                customer.getVersion()
        );
    }
}
~~~

Ưu điểm:
- Dễ đọc và debug.
- Không cần annotation processor.
- Kiểm soát rõ field nào được expose.
- Dễ thêm logic định dạng đơn giản.

Nhược điểm:
- Có thể lặp code khi nhiều DTO.
- Khi thêm field, phải cập nhật mapper thủ công.
- Mapping nested graph lớn có thể dài.

Với API có số lượng DTO vừa phải, mapping thủ công thường là lựa chọn tốt vì thể hiện rõ contract.

## 10. Mapping bằng MapStruct

MapStruct sinh mapper implementation lúc compile, giúp tránh reflection runtime và phát hiện một số mapping thiếu/sai sớm.

Mapper response:

~~~java
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;
import org.mapstruct.ReportingPolicy;

@Mapper(
    componentModel = "spring",
    unmappedTargetPolicy = ReportingPolicy.ERROR
)
public interface CustomerMapper {

    CustomerResponse toResponse(Customer customer);
}
~~~

Vì CustomerResponse chỉ chứa một số thuộc tính công khai và tên field tương ứng, MapStruct có thể tự ánh xạ các thuộc tính phù hợp. passwordHash không có trong response nên không được đưa ra.

Nếu tên field khác nhau:

~~~java
@Mapper(componentModel = "spring")
public interface CustomerMapper {

    @Mapping(source = "createdAt", target = "registeredAt")
    CustomerDetailResponse toDetail(Customer customer);
}
~~~

Khi dùng MapStruct:
- Cấu hình annotation processor trong Maven/Gradle.
- Dùng componentModel spring để inject mapper.
- Dùng unmappedTargetPolicy phù hợp để phát hiện field chưa map.
- Không để mapper tự động map field nhạy cảm vào DTO.
- Kiểm tra generated source khi mapping phức tạp.
- Dùng @Mapping(ignore = true) tường minh nếu target có field cần service gán riêng.

Không dùng mapper để map nguyên request vào Entity rồi tin rằng các field bị thiếu sẽ luôn an toàn. Hãy chỉ map những field client được phép thay đổi.

## 11. Request DTO và Command có thể tách riêng

Trong ứng dụng lớn, request DTO là hợp đồng HTTP, còn command là yêu cầu nghiệp vụ nội bộ.

Ví dụ:

~~~java
public record CreateCustomerCommand(
        String normalizedName,
        String normalizedEmail,
        String passwordHash
) {
}
~~~

Controller nhận CreateCustomerRequest, service chuẩn hóa và chuyển thành command hoặc application service nhận command đã được chuẩn bị. Tầng domain không cần phụ thuộc vào annotation Jackson hoặc Jakarta Validation.

Một luồng có thể là:

~~~text
HTTP JSON
   |
   v
CreateCustomerRequest
   |
   v
Controller + validation
   |
   v
Application Service
   |
   +--> normalize/authorize/hash
   |
   v
CreateCustomerCommand
   |
   v
Domain/Repository
   |
   v
Customer Entity
~~~

Với ứng dụng nhỏ, không cần thêm Command class nếu nó chỉ sao chép hoàn toàn request DTO. Tách khi hai mô hình có vòng đời, semantics hoặc người tiêu thụ khác nhau.

## 12. DTO không phải lúc nào cũng là projection

DTO thường được tạo bằng cách map từ Entity đã load. Projection có thể cho database chỉ trả những cột cần thiết cho một use case đọc.

Ví dụ interface projection:

~~~java
public interface CustomerSummary {
    Long getId();
    String getName();
    String getEmail();
}
~~~

Repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    List<CustomerSummary> findByStatus(CustomerStatus status);
}
~~~

Spring Data có thể dùng projection để tạo kết quả chỉ gồm thuộc tính cần thiết theo cơ chế projection/provider. Hãy kiểm tra SQL thực tế nếu mục tiêu là giảm cột SELECT hoặc tối ưu truy vấn.

DTO projection qua JPQL constructor expression:

~~~java
@Query("""
    select new com.example.api.CustomerSummaryDto(
        c.id,
        c.name,
        c.email
    )
    from Customer c
    where c.status = :status
    order by c.name
    """)
List<CustomerSummaryDto> findSummaries(
        @Param("status") CustomerStatus status
);
~~~

Constructor DTO phải có tham số đúng thứ tự và kiểu dữ liệu tương ứng. JPQL constructor expression dùng tên class đầy đủ trong biểu thức new.

Dùng projection cho danh sách lớn hoặc màn hình chỉ đọc khi không cần toàn bộ Entity. Dùng Entity khi cần thay đổi trạng thái nghiệp vụ và để JPA dirty checking quản lý.

## 13. Nested DTO cho quan hệ Entity

Ví dụ Order có Customer và nhiều OrderLine. Response có thể biểu diễn dữ liệu cần thiết mà không trả nguyên graph Entity:

~~~java
public record OrderLineResponse(
        Long productId,
        String productName,
        int quantity,
        BigDecimal unitPrice
) {
}

public record OrderResponse(
        Long id,
        String orderNumber,
        String customerName,
        List<OrderLineResponse> lines
) {
}
~~~

Mapper:

~~~java
@Component
public class OrderMapper {

    public OrderResponse toResponse(PurchaseOrder order) {
        List<OrderLineResponse> lines = order.getLines().stream()
                .map(line -> new OrderLineResponse(
                        line.getProduct().getId(),
                        line.getProduct().getName(),
                        line.getQuantity(),
                        line.getUnitPrice()
                ))
                .toList();

        return new OrderResponse(
                order.getId(),
                order.getOrderNumber(),
                order.getCustomer().getName(),
                lines
        );
    }
}
~~~

Đoạn mapping truy cập customer, lines và product. Các quan hệ cần thiết phải được tải trong transaction bằng fetch join, EntityGraph hoặc truy vấn projection phù hợp. Nếu không, mapper có thể gây LazyInitializationException hoặc N+1.

Không expose toàn bộ Customer hoặc Product chỉ để hiển thị vài trường. Nested DTO giúp xác định rõ dữ liệu nào cần xuất hiện trong response.

## 14. Mapping trong hay ngoài transaction?

Nếu mapper truy cập thuộc tính LAZY, hãy thực hiện mapping trong phạm vi transaction và bảo đảm query tải đúng quan hệ.

Ví dụ:

~~~java
@Transactional(readOnly = true)
public OrderResponse findOrder(Long id) {
    PurchaseOrder order = repository.findWithDetailsById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));

    return mapper.toResponse(order);
}
~~~

Repository có thể khai báo EntityGraph:

~~~java
@EntityGraph(attributePaths = {
        "customer",
        "lines",
        "lines.product"
})
Optional<PurchaseOrder> findWithDetailsById(Long id);
~~~

EntityGraph yêu cầu provider tải các quan hệ được chỉ định theo fetch plan. Cần kiểm tra SQL và cardinality; fetch nhiều collection có thể tạo Cartesian multiplication hoặc kết quả trùng dòng tùy query.

Mapping DTO bên trong service transaction giúp response không phụ thuộc vào persistence context sau khi Controller nhận kết quả. Service trả DTO đã hoàn chỉnh, không trả Entity còn quan hệ lazy cần serialize.

## 15. Tránh N+1 khi tạo DTO

N+1 xảy ra khi query đầu lấy danh sách N Entity, sau đó mapper truy cập một quan hệ LAZY và phát sinh thêm truy vấn cho từng Entity.

Ví dụ:
1. Một query lấy 50 Order.
2. Mapper đọc order.getCustomer().getName().
3. Hibernate phát thêm query cho từng Customer nếu chưa được load.
4. Tổng số query có thể tăng gần 1 + N.

Các cách xử lý:
- Dùng projection để lấy trực tiếp customerName.
- Dùng @EntityGraph cho quan hệ cần thiết.
- Dùng fetch join có kiểm soát.
- Dùng batch fetching nếu phù hợp.
- Viết custom query để lấy DTO theo đúng cấu trúc response.

Không thêm fetch join mọi quan hệ một cách máy móc. Chỉ tải dữ liệu endpoint cần, kiểm tra SQL, số dòng và execution plan.

## 16. Cập nhật Entity bằng request DTO

Với cập nhật thông thường, nên load Entity managed rồi áp dụng các field được phép thay đổi:

~~~java
public record UpdateCustomerRequest(
        @NotBlank @Size(max = 120) String name,
        @NotBlank @Email String email
) {
}
~~~

~~~java
@Transactional
public CustomerResponse update(
        Long id,
        UpdateCustomerRequest request) {

    Customer customer = repository.findById(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));

    customer.rename(request.name().trim());
    customer.changeEmail(request.email().trim().toLowerCase(Locale.ROOT));

    return mapper.toResponse(customer);
}
~~~

Không cần tạo Entity mới từ request rồi gọi save() để merge toàn bộ trạng thái. Entity được load trong transaction đang managed; dirty checking sẽ đồng bộ các thay đổi khi commit.

Cách này giữ nguyên field không có trong request, không cho client tự sửa status, version hoặc passwordHash, cho phép service áp dụng rule theo từng field và tránh merge một object thiếu thuộc tính rồi ghi đè dữ liệu.

Nếu cần thay đổi status, hãy có use case riêng như activateCustomer() và kiểm tra quyền/điều kiện chuyển trạng thái.

## 17. PUT và PATCH có semantics khác nhau

PUT thường biểu diễn việc thay thế representation của resource theo contract API. PATCH biểu diễn thay đổi một phần. DTO cần thể hiện rõ semantics đó.

Một DTO có field nullable đơn giản:

~~~java
public record PatchCustomerRequest(
        String name,
        String email
) {
}
~~~

không phân biệt được hai trường hợp:
- Client không gửi email.
- Client gửi email: null.

Nếu null có ý nghĩa “xóa giá trị”, cần một kiểu biểu diễn ba trạng thái: absent, present-null, present-value. Có thể dùng JsonNullable từ thư viện jackson-databind-nullable hoặc một wrapper/command riêng.

Ví dụ ý tưởng với JsonNullable:

~~~java
public record PatchCustomerRequest(
        JsonNullable<String> name,
        JsonNullable<String> email
) {
}
~~~

Service phải kiểm tra field có được gửi hay không trước khi đọc giá trị. Cần cấu hình Jackson module cho JsonNullable và kiểm thử JSON absent/null/value.

Không dùng logic request.email() != null nếu API cần phân biệt absent với explicit null. Với API không cho phép xóa email, có thể đơn giản hóa contract và từ chối null.

## 18. Validation DTO và validation Entity

Validation đầu vào và constraint persistence giải quyết hai vấn đề khác nhau.

| Cơ chế | Mục đích |
|---|---|
| @NotBlank, @Email, @Size trên request DTO | Kiểm tra request có hình thức hợp lệ |
| Kiểm tra ở service/domain | Bảo vệ quy tắc nghiệp vụ |
| @Column(nullable = false) | Mô tả mapping và schema constraint |
| Unique/FK/check constraint trong database | Bảo vệ toàn vẹn dữ liệu ở database |
| Bean Validation trên Entity | Kiểm tra constraint object khi validation lifecycle được kích hoạt |

Không dựa vào @Column(nullable = false) để tạo thông báo lỗi thân thiện cho client. Cũng không dựa vào @Valid request DTO để thay thế unique constraint vì race condition vẫn có thể xảy ra.

Controller có thể dùng:

~~~java
@PostMapping
public CustomerResponse create(
        @Valid @RequestBody CreateCustomerRequest request) {
    return service.create(request);
}
~~~

Dùng @RestControllerAdvice để chuyển lỗi validation và lỗi nghiệp vụ sang response error model nhất quán.

## 19. Bảo mật và mass assignment

Nếu bind JSON trực tiếp vào Entity, client có thể gửi những field không thuộc quyền cập nhật của họ:

~~~json
{
  "name": "An",
  "status": "ACTIVE",
  "role": "ADMIN",
  "passwordHash": "attacker-value",
  "version": 99
}
~~~

Ngay cả khi một số field không được serialize, deserialization vẫn có thể nhận chúng nếu mapping cho phép. Dùng request DTO allow-list giúp chỉ nhận field được thiết kế.

Thực hành:
- Tách Create, Update, Patch DTO theo quyền và semantics.
- Không nhận passwordHash từ client.
- Không để client tự gán ownerId, tenantId, role hoặc status nhạy cảm.
- Kiểm tra authorization ở service/use case.
- Không expose Entity qua JSON.
- Không dùng @JsonIgnore làm ranh giới bảo mật duy nhất.
- Kiểm tra log và error response không làm lộ dữ liệu nhạy cảm.

DTO không tự bảo đảm authorization. Service vẫn phải xác minh người gọi có quyền thao tác trên resource cụ thể.

## 20. Không dùng @JsonIgnore để thay thế DTO

Có thể đánh dấu một thuộc tính Entity bằng @JsonIgnore:

~~~java
@JsonIgnore
private String passwordHash;
~~~

Điều này có thể ngăn Jackson serialize thuộc tính trong cấu hình thông thường, nhưng không giải quyết toàn bộ vấn đề:
- Entity vẫn là API contract.
- Request binding có thể có hành vi khác theo annotation/configuration.
- Các endpoint cần response khác nhau vẫn dùng chung Entity.
- Lazy loading và vòng lặp quan hệ vẫn có thể tồn tại.
- Quyền truy cập field vẫn cần kiểm soát riêng.

DTO cho phép tạo allow-list rõ ràng: field nào xuất hiện trong response thì được khai báo tường minh.

Nếu ứng dụng cần ẩn một vài field trong một endpoint đặc biệt, JsonView hoặc Jackson annotation có thể hữu ích, nhưng với API nhiều use case, DTO thường dễ hiểu và kiểm thử hơn.

## 21. Không để Jackson serialize quan hệ hai chiều của Entity

Ví dụ:
- Customer có List<Order>.
- Order có Customer.

Serialize Customer có thể đi theo orders rồi quay lại customer và tiếp tục lặp. Có thể dùng Jackson annotations như JsonManagedReference/JsonBackReference hoặc JsonIdentityInfo trong một số trường hợp, nhưng các annotation này vẫn gắn API serialization vào Entity graph.

Response DTO tránh vòng lặp bằng cách chọn cấu trúc hữu hạn:

~~~java
public record CustomerResponse(
        Long id,
        String name,
        List<OrderSummaryResponse> orders
) {
}

public record OrderSummaryResponse(
        Long id,
        String orderNumber
) {
}
~~~

OrderSummaryResponse không chứa CustomerResponse lồng lại. Cấu trúc response được thiết kế theo nhu cầu endpoint và không cần phản chiếu toàn bộ quan hệ JPA.

## 22. Projection, DTO mapping và Entity: chọn theo use case

| Nhu cầu | Lựa chọn thường phù hợp |
|---|---|
| Tạo/cập nhật aggregate và áp dụng domain rule | Entity managed trong transaction |
| Trả một response nhỏ từ Entity đã load | Map Entity sang response DTO |
| Danh sách lớn chỉ cần vài cột | Interface/constructor projection |
| Báo cáo tổng hợp | DTO projection hoặc native query |
| Response có nested relation | DTO mapper với fetch plan rõ ràng |
| Nhiều API có contract khác nhau trên cùng Entity | Nhiều response DTO riêng |
| Cập nhật một phần field | Patch DTO/command và áp dụng lên Entity managed |

Không cần map Entity sang DTO rồi lại map DTO sang Entity cho mọi thao tác. Với command update, load Entity managed và gọi phương thức domain thường là đủ. Với truy vấn đọc lớn, projection có thể tránh hydrate Entity không cần thiết.

## 23. Response model và versioning API

Entity có thể thay đổi theo database migration, nhưng API contract cần ổn định hơn. Response DTO cho phép:
- Đổi tên cột mà không đổi JSON field.
- Thêm field response có kiểm soát.
- Duy trì nhiều phiên bản API.
- Trả dữ liệu đã định dạng hoặc tổng hợp.
- Ẩn field nội bộ.
- Thay đổi cách lưu trữ mà không làm client phụ thuộc.

Ví dụ Entity lưu firstName và lastName, nhưng API trả fullName. Mapper có thể ghép hai field:

~~~java
public record CustomerProfileResponse(
        Long id,
        String fullName
) {
}
~~~

~~~java
public CustomerProfileResponse toProfile(Customer customer) {
    return new CustomerProfileResponse(
            customer.getId(),
            customer.getFirstName() + " " + customer.getLastName()
    );
}
~~~

Nếu response field là derived value, xác định rõ format/null behavior và test để tránh API thay đổi ngoài ý muốn.

## 24. Version và optimistic locking qua DTO

Entity có @Version để phát hiện cập nhật đồng thời. Có thể đưa version ra response nếu client cần gửi lại khi cập nhật.

Ví dụ response chứa version:

~~~java
public record CustomerResponse(
        Long id,
        String name,
        Long version
) {
}
~~~

Request update có version mong đợi:

~~~java
public record UpdateCustomerRequest(
        @NotBlank String name,
        @NotNull Long expectedVersion
) {
}
~~~

Service có thể kiểm tra expectedVersion với version Entity đã load, sau đó vẫn dựa vào JPA @Version để bảo vệ ở database khi có race giữa lúc đọc và commit.

Một cách HTTP chuẩn hơn là dùng ETag/If-Match. Không gán trực tiếp giá trị version từ client vào Entity đang managed để ghi đè version do provider quản lý. Version đầu vào là điều kiện kiểm tra, không phải field tùy ý để client cập nhật.

## 25. Xử lý response sau khi lưu Entity

Khi tạo Entity, ID database có thể chỉ được gán sau persist/flush tùy chiến lược sinh khóa. Nếu response cần ID, việc mapping sau repository.save() thường đủ với IDENTITY/sequence và provider tương ứng; nếu cần chắc chắn SQL đã chạy, có thể flush.

Ví dụ:

~~~java
@Transactional
public CustomerResponse create(CreateCustomerRequest request) {
    Customer customer = new Customer(
            request.name(),
            request.email(),
            passwordEncoder.encode(request.password())
    );

    Customer saved = repository.save(customer);

    return mapper.toResponse(saved);
}
~~~

Không gọi saveAndFlush() chỉ để “chắc chắn lưu” nếu không có nhu cầu flush sớm. Commit vẫn xảy ra ở ranh giới transaction; flush không đồng nghĩa commit.

Nếu response cần dữ liệu do database trigger/default tạo, có thể phải refresh hoặc truy vấn lại sau flush tùy mapping/provider. Hãy kiểm tra hành vi thật thay vì giả định mọi generated column đã có trong object ngay sau save().

## 26. Kiểm thử DTO và mapper

Mapper có thể được unit test độc lập:

~~~java
class CustomerMapperTest {

    private final CustomerMapper mapper = new CustomerMapper();

    @Test
    void mapsOnlyPublicCustomerFields() {
        Customer customer =
                new Customer("An", "an@example.com", "secret-hash");

        CustomerResponse response = mapper.toResponse(customer);

        assertEquals("An", response.name());
        assertEquals("an@example.com", response.email());
    }
}
~~~

Đây là ví dụ minh họa; Customer cần getter và các trường tương ứng. Bài test nên xác nhận response không có passwordHash hoặc các field nội bộ.

Với MapStruct, có thể kiểm tra generated mapper thông qua test tương tự. Cấu hình unmappedTargetPolicy ERROR giúp phát hiện target field chưa được map khi compile.

## 27. Kiểm thử API serialization

Không chỉ kiểm tra object DTO; cần kiểm tra JSON contract:

- Response có đúng field name và kiểu dữ liệu không?
- Field nhạy cảm có vắng mặt không?
- Null có được bỏ qua hay trả về theo contract?
- Enum được serialize theo tên hay giá trị riêng?
- Instant có format ISO-8601 và timezone nhất quán không?
- Nested collection có cấu trúc đúng và không lặp?
- Request không thể set status/role/passwordHash/version?
- Validation lỗi trả status và error body đúng?

Ví dụ với MockMvc:

~~~java
mockMvc.perform(post("/api/customers")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "name": "An",
              "email": "an@example.com",
              "password": "correct-horse-battery"
            }
            """))
    .andExpect(status().isCreated())
    .andExpect(jsonPath("$.name").value("An"))
    .andExpect(jsonPath("$.email").value("an@example.com"))
    .andExpect(jsonPath("$.passwordHash").doesNotExist());
~~~

Test này cần controller, service và fixture/mock phù hợp. Nên kiểm tra thêm response không chứa password, role nội bộ hoặc các thuộc tính Entity khác không nằm trong contract.

## 28. Kiểm thử lazy loading và truy vấn

Một integration test cho endpoint chi tiết nên chạy trong cấu hình tương tự production:
1. Lưu Entity và quan hệ.
2. Kết thúc transaction tạo fixture.
3. Gọi service đọc chi tiết.
4. Mapping DTO với fetch plan được chỉ định.
5. Xác nhận không phát sinh LazyInitializationException.
6. Theo dõi SQL count để phát hiện N+1.
7. Xác nhận response có đúng quan hệ cần thiết.

Đừng chỉ chạy mapper trong test có persistence context mở sẵn rồi kết luận endpoint không có lỗi lazy. Open Session in View có thể che giấu việc service không tải dữ liệu đầy đủ; hãy cân nhắc tắt OSIV hoặc test theo ranh giới transaction mà kiến trúc mong muốn.

## 29. Những lỗi thường gặp

**Trả Entity trực tiếp từ Controller**

API bị gắn với schema và quan hệ persistence. Trả response DTO theo contract endpoint.

**Bind request JSON vào Entity**

Client có thể sửa field nội bộ hoặc field không được phép. Dùng request DTO allow-list.

**Dùng cùng một DTO cho create, update và response**

Các thao tác có field và semantics khác nhau. Tách DTO theo use case khi contract khác nhau.

**Map password hoặc passwordHash vào response**

Lộ dữ liệu nhạy cảm. Không khai báo field đó trong response model và kiểm thử JSON.

**Map Entity sang DTO sau khi transaction đã đóng**

Mapper có thể truy cập quan hệ LAZY và lỗi. Map trong service transaction với fetch plan rõ.

**Mapper gây N+1**

Truy cập quan hệ LAZY trong vòng lặp. Dùng projection, EntityGraph hoặc fetch join có kiểm soát.

**Merge Entity dựng từ request DTO**

Field null/default có thể ghi đè dữ liệu. Load Entity managed rồi áp dụng field được phép sửa.

**Dùng DTO như một bản sao toàn bộ Entity**

DTO vẫn có thể chứa quá nhiều field và làm API contract phụ thuộc persistence. Thiết kế theo dữ liệu endpoint cần.

**Dùng @JsonIgnore làm ranh giới bảo mật duy nhất**

Entity vẫn là response model và có thể có đường serialize khác. Dùng DTO allow-list.

**Không phân biệt absent và null trong PATCH**

Ứng dụng không biết client muốn giữ nguyên hay xóa field. Dùng kiểu ba trạng thái hoặc contract PATCH rõ ràng.

**Không kiểm tra quyền dù đã có DTO**

DTO chỉ giới hạn field; service vẫn phải xác minh caller có quyền sửa resource.

**Trả DTO projection nhưng query không tải đủ dữ liệu**

Constructor/field mapping có thể sai hoặc gây query bổ sung. Kiểm tra SQL, mapping và test integration.

## 30. Quy trình thiết kế ranh giới Entity–DTO

Khi xây dựng một endpoint Spring Data JPA:

1. Xác định dữ liệu client được phép gửi và tạo request DTO riêng.
2. Thêm validation cho hình thức đầu vào.
3. Xác định quy tắc nghiệp vụ và quyền truy cập trong service.
4. Load hoặc tạo Entity trong transaction.
5. Chỉ thay đổi field được phép qua phương thức domain/service.
6. Dùng Repository để lưu Entity và để JPA quản lý lifecycle.
7. Chọn response DTO theo contract endpoint.
8. Map thủ công hoặc dùng MapStruct; không để mapper quyết định nghiệp vụ.
9. Nếu cần ít cột hoặc danh sách lớn, cân nhắc projection.
10. Nếu response cần quan hệ LAZY, xác định fetch plan trước khi mapping.
11. Kiểm tra JSON không lộ field nội bộ và không có vòng lặp.
12. Kiểm thử validation, authorization, mapper, transaction, lazy loading và query count.
13. Giữ API contract ổn định khi Entity/schema thay đổi.

## 31. Kết luận

Entity là mô hình persistence do JPA quản lý; request DTO và response DTO là hợp đồng dữ liệu của từng use case/API. Tách các mô hình này giúp giới hạn field client được gửi, tránh lộ dữ liệu nhạy cảm, kiểm soát JSON và giảm phụ thuộc API vào schema database. Controller nhận request DTO, Service áp dụng quy tắc nghiệp vụ trong transaction, Repository làm việc với Entity, Mapper tạo response DTO. Với danh sách hoặc truy vấn đọc chỉ cần vài cột, projection có thể hiệu quả hơn việc load toàn bộ Entity.

Hãy map Entity sang DTO trong transaction khi cần quan hệ LAZY, dùng EntityGraph/projection để tránh N+1, load Entity managed rồi áp dụng command cho cập nhật một phần và kiểm thử JSON contract. DTO không thay thế authorization hay database constraint; nó là ranh giới rõ ràng để ứng dụng chủ động quyết định dữ liệu nào được nhận và được công bố.

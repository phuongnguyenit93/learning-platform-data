# Phân biệt DTO trả kết quả truy vấn và DTO nhận dữ liệu cập nhật

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt DTO dùng để trả dữ liệu đọc với DTO dùng để nhận lệnh tạo/cập nhật.
- Giải thích vì sao hai loại DTO có field, validation và vòng đời khác nhau.
- Dùng interface projection hoặc constructor projection để truy vấn dữ liệu cần thiết bằng Spring Data JPA.
- Thiết kế request DTO có validation và chỉ cho phép cập nhật các field được nghiệp vụ chấp nhận.
- Cập nhật managed entity trong transaction thay vì bind request trực tiếp vào entity rồi merge.
- Xử lý đúng semantics của PUT, PATCH, field bị thiếu và field có giá trị null.
- Dùng version để kiểm soát cập nhật đồng thời và kiểm thử cả luồng đọc lẫn ghi.

## 1. DTO là gì và vì sao cần tách theo chiều dữ liệu?

DTO (Data Transfer Object) là kiểu dữ liệu được dùng để chuyển dữ liệu qua một ranh giới, chẳng hạn giữa repository và service hoặc giữa API và client. DTO thường chỉ chứa dữ liệu cần truyền, không đại diện cho persistence context và không có identity do JPA quản lý.

Trong một ứng dụng Spring Data JPA, có ít nhất hai hướng dữ liệu thường gặp:

- **Read DTO / response DTO**: mang dữ liệu từ ứng dụng ra ngoài, thường phục vụ màn hình, báo cáo hoặc API response.
- **Write DTO / request DTO / command DTO**: mang dữ liệu từ client vào ứng dụng để yêu cầu tạo hoặc thay đổi trạng thái.

Hai hướng này có mục đích khác nhau. Một màn hình danh sách có thể chỉ cần ID, tên và trạng thái. Một lệnh cập nhật hồ sơ có thể cần tên, email, quy tắc validation và thông tin kiểm soát phiên bản.

Không nên dùng một DTO duy nhất cho cả hai chiều chỉ vì các field có vẻ giống nhau. Khi nhu cầu đọc và ghi thay đổi độc lập, một DTO dùng chung dễ trở thành kiểu dữ liệu quá rộng, khó validation và có thể làm lộ field nội bộ.

## 2. Read DTO: trả về đúng dữ liệu người gọi cần

Read DTO mô tả dữ liệu mà use case đọc cần cung cấp. Nó có thể:

- Chỉ chứa một phần field của entity.
- Kết hợp dữ liệu từ nhiều entity hoặc bảng.
- Chứa giá trị tổng hợp như count, total, average.
- Đổi tên field để phù hợp API contract.
- Không chứa field nội bộ như password hash, audit metadata hoặc thông tin kỹ thuật không cần công khai.

Ví dụ, trang danh sách khách hàng chỉ cần:

~~~java
package com.example.customer;

public record CustomerListItem(
        Long id,
        String name,
        String email
) {
}
~~~

Record phù hợp cho DTO bất biến. Nó tự cung cấp constructor, accessor, equals, hashCode và toString theo các component.

Read DTO không cần có annotation `@Entity`, `@Id` hoặc được EntityManager quản lý. Nó là kết quả đọc, không phải đối tượng cần dirty checking.

### Vì sao không trả thẳng entity?

Trả entity trực tiếp ra API có thể gây ra:

- **Lộ dữ liệu**: entity có thể chứa field nội bộ không nên công khai.
- **Coupling**: thay đổi mapping database có thể vô tình làm thay đổi JSON contract.
- **Lazy loading**: serializer có thể truy cập association sau khi persistence context đóng.
- **N+1 query**: serialize một collection có thể kích hoạt nhiều truy vấn.
- **Vòng lặp object graph**: quan hệ hai chiều có thể khiến JSON serialize đệ quy.
- **Over-fetching**: API tải nhiều field/association hơn use case cần.

Read DTO tạo một ranh giới rõ ràng giữa mô hình persistence và dữ liệu trả ra ngoài.

## 3. Tạo Read DTO bằng constructor projection

Spring Data JPA hỗ trợ JPQL constructor expression để tạo DTO trực tiếp từ truy vấn.

Giả sử entity Customer có các field `id`, `name`, `email` và `active`. Repository có thể khai báo:

~~~java
package com.example.customer;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Query("""
        select new com.example.customer.CustomerListItem(
            c.id,
            c.name,
            c.email
        )
        from Customer c
        where c.active = true
        order by c.name
        """)
    List<CustomerListItem> findActiveCustomerItems();
}
~~~

JPQL dùng tên entity và thuộc tính Java, không dùng tên bảng/cột SQL. Phần `new` cần tên lớp DTO đầy đủ (fully qualified class name). Thứ tự và kiểu các biểu thức phải khớp constructor của DTO.

Kết quả là các đối tượng CustomerListItem. Chúng không phải Customer entity và không được theo dõi bằng dirty checking. Vì vậy, không dùng read DTO làm đối tượng để cập nhật trực tiếp entity.

### Khi nào constructor projection phù hợp?

- Cần kiểu kết quả rõ ràng, ổn định.
- Cần lấy field từ nhiều entity hoặc phép aggregate.
- Muốn tránh tải toàn bộ entity.
- Muốn định nghĩa rõ shape của kết quả tại repository.

Nếu query có nhiều phép join, group by hoặc field tính toán, DTO projection thường giúp use case đọc rõ ràng hơn.

## 4. Interface projection

Spring Data JPA cũng hỗ trợ interface projection:

~~~java
public interface CustomerNameView {
    Long getId();
    String getName();
}
~~~

Repository:

~~~java
List<CustomerNameView> findByActiveTrue();
~~~

Spring Data có thể tạo projection proxy chỉ hiển thị các accessor được khai báo. Với closed projection, các property được biết trước nên Spring Data có thể tối ưu phần dữ liệu cần lấy tùy query và provider.

Projection có thể dùng nested property, nhưng truy cập association lồng nhau có thể yêu cầu join và tải thêm dữ liệu. Không giả định rằng mọi interface projection luôn chỉ sinh đúng một SELECT đơn giản.

### So sánh hai cách đọc

| Tiêu chí | Interface projection | Constructor DTO projection |
|---|---|---|
| Khai báo | Interface với getter | Class hoặc record có constructor |
| Kết quả | Thường là projection proxy | Đối tượng DTO được tạo qua constructor |
| Kiểm soát kiểu | Accessor định nghĩa shape | Constructor định nghĩa shape |
| JPQL tường minh | Có thể dùng query method hoặc @Query | Thường dùng select new |
| Phù hợp | View đơn giản, ít field | Báo cáo hoặc kết quả có cấu trúc rõ |

Chọn theo độ phức tạp và khả năng bảo trì. Đừng tạo projection chỉ để thay đổi tên một field nếu một DTO rõ ràng hơn cho API.

## 5. Write DTO: nhận một lệnh thay đổi

Write DTO mô tả dữ liệu client được phép gửi để yêu cầu một hành động. Nó thường có:

- Các field mà use case cho phép tạo hoặc cập nhật.
- Validation đầu vào.
- Kiểu dữ liệu phù hợp với API.
- Có thể có thông tin version hoặc idempotency key nếu nghiệp vụ cần.
- Không nhất thiết phải chứa mọi field của entity.

Ví dụ request cập nhật hồ sơ Customer:

~~~java
package com.example.customer;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record UpdateCustomerRequest(
        @NotBlank
        @Size(max = 120)
        String name,

        @NotBlank
        @Email
        @Size(max = 254)
        String email
) {
}
~~~

Đây là DTO nhận dữ liệu từ client. Annotation validation mô tả quy tắc của request; nó không tự thay thế constraint database hoặc quy tắc domain.

Controller kích hoạt validation bằng `@Valid`:

~~~java
@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    @PutMapping("/{id}")
    public ResponseEntity<Void> update(
            @PathVariable Long id,
            @Valid @RequestBody UpdateCustomerRequest request) {

        service.update(id, request);
        return ResponseEntity.noContent().build();
    }
}
~~~

Trong ví dụ này, PUT mang nghĩa thay thế toàn bộ phần hồ sơ mà request quản lý. Vì vậy, name và email đều bắt buộc. Nếu API chỉ cho phép đổi một vài field, hãy thiết kế PATCH hoặc endpoint command riêng thay vì vô tình coi field thiếu là null.

## 6. Cập nhật managed entity bằng dữ liệu từ Write DTO

Một luồng cập nhật an toàn thường có các bước:

1. Nhận request DTO và validate cấu trúc đầu vào.
2. Tải entity cần cập nhật trong transaction.
3. Kiểm tra quyền và điều kiện nghiệp vụ.
4. Áp dụng từng field được phép thay đổi.
5. Để dirty checking ghi thay đổi khi transaction flush/commit.

Entity Customer:

~~~java
package com.example.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, unique = true, length = 254)
    private String email;

    @Column(nullable = false)
    private boolean active;

    protected Customer() {
    }

    public void updateProfile(String name, String email) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("email must not be blank");
        }

        this.name = name;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Service:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void update(Long id, UpdateCustomerRequest request) {
        Customer customer = repository.findById(id)
            .orElseThrow(() ->
                new EntityNotFoundException("Customer not found: " + id)
            );

        customer.updateProfile(request.name(), request.email());

        // customer đang managed; dirty checking lưu thay đổi khi commit.
    }
}
~~~

Không cần gọi `repository.save(customer)` lại cho entity vừa được tải trong cùng transaction. Entity đang managed; dirty checking sẽ phát hiện thay đổi. Gọi save có thể vẫn hoạt động, nhưng không cần thiết cho luồng này.

### Vì sao không map request thành entity rồi merge?

Cách làm rủi ro:

~~~java
Customer customer = mapper.toEntity(request);
customer.setId(id);
repository.save(customer);
~~~

Nếu mapper không có đủ field, các field không được gửi có thể trở thành null hoặc giá trị mặc định. Spring Data có thể đi theo nhánh merge và sao chép trạng thái đó vào managed instance, gây mất dữ liệu.

Cách tải entity trước rồi áp dụng thay đổi giúp service kiểm soát field nào được cập nhật, bảo vệ invariant và kiểm tra quyền trên đúng đối tượng.

## 7. Validation của request và validation của domain

Có nhiều lớp kiểm tra khác nhau:

| Lớp | Trách nhiệm | Ví dụ |
|---|---|---|
| Request validation | Kiểm tra hình dạng và ràng buộc đầu vào | @NotBlank, @Email, @Size |
| Domain validation | Bảo vệ quy tắc nghiệp vụ | Email không được trùng trong tenant; không đổi hồ sơ khi account bị khóa |
| Database constraint | Bảo vệ tính toàn vẹn cuối cùng | NOT NULL, UNIQUE, FOREIGN KEY, CHECK |
| Authorization | Kiểm tra người gọi có quyền thực hiện hành động | Chỉ chủ tài khoản hoặc admin được cập nhật |

Một request hợp lệ về cú pháp vẫn có thể vi phạm nghiệp vụ. Ví dụ email có định dạng hợp lệ nhưng đã thuộc về một Customer khác.

Kiểm tra trùng ở service có thể đưa ra lỗi thân thiện, nhưng unique constraint ở database vẫn cần thiết để xử lý race condition giữa các transaction đồng thời.

Không dựa vào validation DTO để bảo đảm database luôn đúng. Dữ liệu có thể được ghi bởi batch job, script, service khác hoặc migration.

## 8. PUT và PATCH có semantics khác nhau

Write DTO cần phù hợp với kiểu cập nhật mà API công bố.

### PUT: thay thế phần tài nguyên được định nghĩa

Với PUT, request thường chứa đầy đủ các field thuộc phần tài nguyên mà endpoint quản lý. Nếu một field bắt buộc không có, request bị từ chối. Ví dụ `UpdateCustomerRequest` ở trên yêu cầu cả name và email.

### PATCH: cập nhật một phần

Với PATCH, field bị thiếu thường có nghĩa là giữ nguyên. Field có giá trị null có thể có nghĩa xóa giá trị, nếu API contract cho phép. Field có giá trị cụ thể thì cập nhật.

Ví dụ JSON:

~~~json
{}
~~~

Không yêu cầu thay đổi field nào.

~~~json
{"name": "An Nguyen"}
~~~

Chỉ cập nhật name.

~~~json
{"email": null}
~~~

Yêu cầu xóa email, nếu domain cho phép và API định nghĩa null là lệnh xóa.

~~~json
{"email": "an@example.com"}
~~~

Cập nhật email sang giá trị mới.

Một DTO Java thông thường có field nullable có thể không phân biệt được field không xuất hiện và field xuất hiện với null sau khi deserialize. Nếu PATCH cần semantics này, phải giữ thông tin field presence.

### Dùng JsonNode để nhận biết field presence

Ví dụ xử lý riêng field email:

~~~java
JsonNode body = objectMapper.readTree(requestBody);

if (!body.has("email")) {
    // Field vắng mặt: giữ nguyên email hiện tại.
} else if (body.get("email").isNull()) {
    // Field có null: xóa email nếu domain cho phép.
} else {
    String email = body.get("email").asText();
    // Validate và cập nhật email.
}
~~~

Một lựa chọn khác là wrapper như `JsonNullable<T>` từ thư viện phù hợp, hoặc một kiểu nội bộ `FieldUpdate<T>` có cờ `present`. Cần cấu hình deserializer để wrapper phân biệt field vắng mặt với explicit null; chỉ thêm một field Java nullable là chưa đủ.

Không tự động biến chuỗi rỗng thành null. `""`, chuỗi chỉ có khoảng trắng và JSON null là các đầu vào khác nhau; quy tắc normalize phải được API/domain định nghĩa.

## 9. Không dùng response DTO làm request DTO

Một response có thể chứa các field chỉ đọc:

~~~java
public record CustomerDetailsResponse(
        Long id,
        String name,
        String email,
        boolean active,
        Long version,
        Instant createdAt
) {
}
~~~

Không nên dùng nguyên kiểu này làm request cập nhật. Client có thể gửi `id`, `active`, `createdAt` hoặc field nội bộ mà endpoint không được phép thay đổi.

Nếu controller bind response DTO trực tiếp vào entity hoặc mapper sao chép tất cả field, có thể xuất hiện mass assignment: client thay đổi những thuộc tính mà họ không được phép kiểm soát.

Hãy tạo request DTO riêng, chỉ liệt kê field có thể thay đổi trong use case. Nếu cần bật/tắt tài khoản, nên dùng command rõ nghĩa như `ChangeCustomerStatusRequest` hoặc endpoint riêng có authorization và domain rule tương ứng.

## 10. Phân biệt DTO với Entity và Mapper

| Kiểu | Có JPA identity? | Được dirty checking? | Mục đích |
|---|---:|---:|---|
| Entity | Có | Có khi managed | Mô hình persistence/domain |
| Read DTO | Không | Không | Trả dữ liệu đọc |
| Write DTO | Không | Không | Nhận lệnh/dữ liệu đầu vào |
| Projection interface | Không phải entity | Không | Hiển thị một tập property truy vấn |

Mapper chuyển đổi dữ liệu giữa DTO và domain/entity. Có thể dùng mapping thủ công, MapStruct hoặc thư viện tương tự. Dù dùng công cụ nào, quy tắc cập nhật vẫn cần rõ ràng:

- Không tự động copy ID từ request nếu ID được lấy từ path.
- Không copy version hoặc trạng thái bảo mật nếu client không được quyền đặt.
- Không ghi đè field không có trong PATCH.
- Không thay association bằng object chỉ có ID mà chưa kiểm tra tồn tại và quyền.
- Không map collection tùy tiện nếu thao tác thêm/xóa phần tử có quy tắc domain riêng.

Mapper giảm code lặp nhưng không thay thế quyết định nghiệp vụ.

## 11. Optimistic locking và version trong luồng cập nhật

Entity Customer ở ví dụ có:

~~~java
@Version
private Long version;
~~~

JPA provider dùng version để phát hiện hai transaction cùng cập nhật một entity từ trạng thái cũ. Khi transaction ghi với version không còn khớp, thao tác có thể thất bại bằng optimistic locking exception.

Nếu API cần phát hiện client đang sửa dữ liệu cũ, có thể trả version trong response DTO và nhận version mong đợi trong request hoặc HTTP ETag/If-Match.

Ví dụ response:

~~~json
{
  "id": 10,
  "name": "An",
  "email": "an@example.com",
  "version": 4
}
~~~

Client gửi version đã đọc khi cập nhật. Service có thể kiểm tra sớm để trả thông báo xung đột thân thiện; JPA `@Version` vẫn là cơ chế bảo vệ cuối cùng vì một transaction khác có thể cập nhật sau bước kiểm tra đó.

Không bỏ `@Version` chỉ vì API có trường version. Kiểm tra ở service và optimistic locking tại database giải quyết hai thời điểm khác nhau.

## 12. Transaction, association và cập nhật collection

Write DTO có thể chứa dữ liệu lồng nhau như địa chỉ hoặc danh sách dòng hàng. Không nên map toàn bộ request thành object graph rồi merge mà không kiểm tra.

Với association:

1. Tải aggregate root trong transaction.
2. Xác thực các entity liên quan tồn tại và người gọi có quyền sử dụng.
3. Gọi phương thức nghiệp vụ để thêm, sửa hoặc gỡ association.
4. Giữ owning side và inverse side đồng bộ.
5. Chỉ dùng cascade/orphanRemoval khi phù hợp vòng đời domain.

Ví dụ, một request thêm sản phẩm vào đơn hàng không nên tạo một Product mới chỉ với ID rồi cascade persist. Hãy tải Product đã tồn tại hoặc tham chiếu entity hợp lệ theo quy tắc domain.

Với collection PATCH, cần định nghĩa rõ request chứa danh sách thay thế toàn bộ hay chỉ các phần tử cần thêm/xóa. Hai ý nghĩa này khác nhau và cần DTO/command khác nhau.

## 13. Kiểm thử riêng cho đọc và ghi

Read DTO test nên xác nhận:

- Query trả đúng số lượng và đúng field.
- Constructor projection khớp thứ tự/kiểu constructor.
- Field không cần thiết không bị tải hoặc lộ ra.
- Sort, pagination và aggregate đúng.
- Association null được biểu diễn đúng.

Write DTO test nên xác nhận:

- Validation từ chối input sai.
- Chỉ field được phép mới thay đổi.
- Field không có trong PATCH được giữ nguyên.
- Explicit null chỉ xóa dữ liệu khi contract cho phép.
- Quy tắc domain và authorization được thực thi.
- Unique constraint và foreign key bảo vệ dữ liệu.
- Optimistic locking phát hiện cập nhật đồng thời.

Ví dụ test cho constructor projection:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void returnsOnlyFieldsNeededByCustomerList() {
        List<CustomerListItem> result =
                repository.findActiveCustomerItems();

        assertEquals(1, result.size());
        assertEquals("An", result.get(0).name());
        assertEquals("an@example.com", result.get(0).email());
    }
}
~~~

Test giả định dữ liệu test đã được seed với đúng một Customer active. Đây là integration test cho query projection; không cần persist hoặc merge CustomerListItem vì nó là DTO.

Ví dụ test cập nhật nên chạy trong transaction phù hợp, flush và clear persistence context trước khi nạp lại entity để xác nhận database đã lưu đúng trạng thái. Với PATCH, tạo test riêng cho field thiếu, explicit null và giá trị cụ thể.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| API trả quá nhiều field | Trả entity hoặc dùng DTO dùng chung quá rộng | Tạo read DTO theo use case |
| DTO projection không khởi tạo được | Constructor sai thứ tự hoặc kiểu tham số | Đối chiếu select expression và constructor |
| Cập nhật làm field khác thành null | Map request thiếu field thành entity rồi merge | Tải managed entity và áp dụng field được phép |
| Client thay đổi được ID/trạng thái nội bộ | Bind request vào entity/response DTO | Dùng write DTO allowlist |
| PATCH không phân biệt field thiếu và null | DTO nullable thông thường gộp hai trạng thái | Dùng JsonNode hoặc tri-state wrapper |
| Field null không được xóa | Service coi null là không cập nhật | Xác định contract và xử lý explicit null riêng |
| Hai người ghi đè thay đổi của nhau | Không có concurrency control | Dùng @Version và xử lý optimistic locking |
| Validation hợp lệ nhưng database vẫn có dữ liệu trùng | Chỉ kiểm tra ở service | Tạo unique constraint ở database |
| LazyInitializationException khi trả entity | Serializer truy cập association ngoài transaction | Trả DTO/projection |
| Mapper ghi đè association sai | Copy object graph mà không kiểm tra ownership | Tải entity liên quan và gọi phương thức domain |

## Quy trình chọn DTO

1. Xác định dữ liệu đi vào hay đi ra khỏi use case.
2. Nếu đi ra, thiết kế read DTO theo đúng field và shape mà người gọi cần.
3. Chọn interface projection hoặc constructor DTO projection cho truy vấn.
4. Nếu đi vào, thiết kế request/command DTO chỉ gồm field được phép thay đổi.
5. Đặt validation ở request, quy tắc nghiệp vụ ở domain/service và constraint cuối cùng ở database.
6. Tải managed entity trong transaction rồi áp dụng thay đổi có chủ đích.
7. Với PATCH, giữ khác biệt giữa field thiếu, null và giá trị.
8. Dùng version/ETag nếu cần kiểm soát cập nhật đồng thời.
9. Viết test độc lập cho query projection và update command.

## Checklist trước khi merge

- [ ] Read DTO và Write DTO có mục đích riêng.
- [ ] Read DTO chỉ trả field cần thiết và không lộ dữ liệu nội bộ.
- [ ] Constructor projection có đúng package, thứ tự và kiểu constructor.
- [ ] Write DTO chỉ nhận field được phép thay đổi.
- [ ] Request validation không bị nhầm với domain validation hoặc database constraint.
- [ ] Service tải managed entity và áp dụng thay đổi trong transaction.
- [ ] Không merge partial entity được dựng từ request DTO.
- [ ] PUT/PATCH có semantics rõ ràng cho field thiếu và null.
- [ ] Association được kiểm tra quyền sở hữu và vòng đời.
- [ ] Optimistic locking được dùng khi cần chống lost update.
- [ ] Read projection và write flow đều có integration test.

## Kết luận

Read DTO mô tả dữ liệu ứng dụng muốn trả về; Write DTO mô tả lệnh và field client được phép gửi vào. Read DTO thường được tạo bằng interface projection hoặc constructor projection và không được JPA quản lý. Write DTO cần validation và phải được áp dụng lên managed entity trong transaction theo quy tắc nghiệp vụ. Tách hai loại DTO giúp kiểm soát dữ liệu công khai, tránh mass assignment, ngăn partial request ghi đè field thành null và làm rõ semantics PUT/PATCH. Hãy kiểm thử riêng truy vấn đọc, cập nhật, field presence và optimistic locking.

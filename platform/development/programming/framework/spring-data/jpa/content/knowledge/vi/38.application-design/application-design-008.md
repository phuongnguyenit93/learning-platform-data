# Thiết kế bộ lọc an toàn, giới hạn phân trang và kiểm soát quyền dữ liệu

## Mục tiêu

Một API tìm kiếm an toàn cần giải quyết đồng thời ba vấn đề: người dùng được phép lọc theo trường nào, mỗi request được phép đọc bao nhiêu dữ liệu và người dùng có quyền nhìn thấy những bản ghi nào. Chỉ giới hạn page size là chưa đủ nếu query vẫn đọc dữ liệu của tenant khác; chỉ kiểm tra quyền ở controller cũng chưa đủ nếu repository query, count query hoặc export không áp dụng cùng phạm vi dữ liệu.

Bài này dùng Spring Data JPA, Specification và Spring Security để xây dựng một luồng tìm kiếm có kiểm soát từ HTTP request tới database. Các nguyên tắc chính là:

- Nhận filter qua DTO có kiểu và validate đầu vào.
- Chỉ cho phép sort theo danh sách property do server định nghĩa.
- Giới hạn page size, offset và khoảng tìm kiếm.
- Luôn ghép tenant/owner scope lấy từ danh tính đã xác thực vào predicate ở server.
- Áp dụng cùng phạm vi quyền cho danh sách, count, exists, chi tiết, cập nhật, xóa và export.
- Trả DTO chỉ chứa dữ liệu caller được phép xem.
- Kiểm thử cả kết quả lẫn metadata phân trang bằng dữ liệu nhiều tenant/người sở hữu.

Sau bài này, bạn có thể thiết kế filter không nhận entity trực tiếp từ client, ngăn SQL/order injection, giảm nguy cơ data enumeration và tránh truy vấn quá lớn.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Data JPA, Jakarta Persistence và Spring Security 6. Cần có các dependency JPA, Web, Validation, Security và test support tương ứng.

## 1. Ba lớp kiểm soát phải đi cùng nhau

Một endpoint tìm kiếm thường có ba lớp chính:

| Lớp | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Filter validation | Người dùng được gửi tiêu chí gì? | name tối đa 100 ký tự, status thuộc enum |
| Resource/pagination control | Một request được đọc bao nhiêu dữ liệu? | size tối đa 100, offset không quá sâu |
| Data authorization | Người dùng được nhìn thấy hàng nào? | tenant hiện tại và owner hiện tại |

Ba lớp này giải quyết các rủi ro khác nhau:

- Validation ngăn input sai định dạng, quá dài hoặc ngoài nghiệp vụ.
- Pagination giới hạn chi phí và kích thước response.
- Authorization giới hạn dữ liệu được truy cập.

Ví dụ, request có page size là 20 vẫn có thể làm lộ 20 bản ghi của tenant khác nếu query thiếu tenant predicate. Tương tự, endpoint trả đúng các hàng nhưng count query không có tenant scope vẫn có thể tiết lộ tổng số nhân viên trong tenant khác.

Vì vậy, phạm vi quyền phải được áp dụng ngay trong query ở tầng service/repository, không phụ thuộc vào việc giao diện có ẩn nút hoặc field hay không.

## 2. Không bind trực tiếp entity từ request

Không nên nhận entity JPA làm tham số tìm kiếm:

```java
@GetMapping("/employees")
public Page<Employee> search(
        @ModelAttribute Employee employee,
        Pageable pageable
) {
    // Không dùng cách bind entity này cho API công khai.
}
```

Entity thường chứa các field nội bộ như tenantId, ownerId, role, salary, audit fields hoặc trạng thái workflow. Nếu bind trực tiếp, client có thể thử gửi những thuộc tính không được phép điều khiển.

Tạo DTO riêng chỉ chứa các filter đã được duyệt:

```java
public record EmployeeFilterRequest(
        @Size(max = 100)
        String name,

        EmployeeStatus status,

        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
        Instant createdFrom,

        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
        Instant createdTo
) {
    public EmployeeFilter toFilter() {
        return new EmployeeFilter(
                name,
                status,
                createdFrom,
                createdTo
        );
    }
}
```

Filter nội bộ:

```java
public record EmployeeFilter(
        String name,
        EmployeeStatus status,
        Instant createdFrom,
        Instant createdTo
) {
}
```

Enum trạng thái:

```java
public enum EmployeeStatus {
    ACTIVE,
    INACTIVE,
    SUSPENDED
}
```

DTO này không có tenantId, ownerId hoặc quyền truy cập. Những giá trị đó phải đến từ principal/security context do server xác thực, không lấy từ query string hoặc JSON body do client gửi.

Nếu client gửi thêm field không được khai báo, framework có thể bỏ qua hoặc từ chối tùy cấu hình binding. Dù hành vi nào được chọn, service vẫn chỉ dùng những thuộc tính đã có trong DTO và không map request sang entity một cách tự động.

## 3. Validate filter trước khi tạo query

Validation cần bao gồm cả định dạng từng field và quan hệ giữa nhiều field.

Ví dụ các quy tắc:

- name tối đa 100 ký tự.
- status phải là một giá trị trong enum.
- createdFrom phải nhỏ hơn createdTo.
- Khoảng thời gian tìm kiếm không vượt quá giới hạn nghiệp vụ.
- Chuỗi chỉ có khoảng trắng được xem là chưa nhập.
- Giới hạn số lượng tiêu chí hoặc yêu cầu ít nhất một filter khi phạm vi tìm kiếm quá rộng.

Kiểm tra khoảng thời gian ở service:

```java
private void validateFilter(EmployeeFilter filter) {
    if (filter.createdFrom() != null
            && filter.createdTo() != null
            && !filter.createdFrom().isBefore(filter.createdTo())) {
        throw new IllegalArgumentException(
                "createdFrom must be earlier than createdTo"
        );
    }

    if (filter.createdFrom() != null
            && filter.createdTo() != null
            && Duration.between(
                    filter.createdFrom(),
                    filter.createdTo()
            ).compareTo(Duration.ofDays(366)) > 0) {
        throw new IllegalArgumentException(
                "Search range must not exceed 366 days"
        );
    }
}
```

Giới hạn 366 ngày chỉ là chính sách minh họa. Ứng dụng cần chọn khoảng thời gian phù hợp với nghiệp vụ, dung lượng dữ liệu và khả năng database.

Không nên tự động biến một filter sai thành filter khác mà không có hợp đồng rõ ràng. Ví dụ, nếu người dùng gửi createdFrom lớn hơn createdTo, trả lỗi validation 400 thường dễ hiểu hơn việc âm thầm đảo hai giá trị.

### 3.1. Chuẩn hóa chuỗi

Chuẩn hóa chuỗi ở một nơi thống nhất:

```java
private String normalizeName(String name) {
    if (name == null || name.isBlank()) {
        return null;
    }
    return name.trim();
}
```

Không tự ý thay đổi Unicode hoặc bỏ dấu nếu nghiệp vụ chưa định nghĩa rõ semantics tìm kiếm tiếng Việt. Cách so sánh chữ hoa/thường và dấu còn phụ thuộc collation của database.

## 4. Thiết kế entity và repository

Ví dụ entity Employee có tenant và owner để minh họa row-level authorization:

```java
package com.example.demo.employee;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(
    name = "employees",
    indexes = {
        @Index(
            name = "ix_employee_tenant_created_id",
            columnList = "tenant_id, created_at, id"
        ),
        @Index(
            name = "ix_employee_tenant_owner_created_id",
            columnList = "tenant_id, owner_id, created_at, id"
        )
    }
)
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private UUID tenantId;

    @Column(name = "owner_id", nullable = false)
    private UUID ownerId;

    @Column(nullable = false, length = 120)
    private String name;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private EmployeeStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected Employee() {
    }

    public Employee(
            UUID tenantId,
            UUID ownerId,
            String name,
            EmployeeStatus status,
            Instant createdAt
    ) {
        this.tenantId = tenantId;
        this.ownerId = ownerId;
        this.name = name;
        this.status = status;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public UUID getTenantId() {
        return tenantId;
    }

    public UUID getOwnerId() {
        return ownerId;
    }

    public String getName() {
        return name;
    }

    public EmployeeStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

Hai index trong ví dụ minh họa hai kiểu truy vấn phổ biến: quản trị viên đọc trong tenant và người dùng chỉ đọc bản ghi của mình. Index thực tế phải dựa trên filter, sort, cardinality và execution plan của database; không sao chép index này một cách máy móc.

Repository:

```java
package com.example.demo.employee;

import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface EmployeeRepository
        extends JpaRepository<Employee, Long>,
                JpaSpecificationExecutor<Employee> {

    Optional<Employee> findByIdAndTenantId(
            Long id,
            UUID tenantId
    );

    Optional<Employee> findByIdAndTenantIdAndOwnerId(
            Long id,
            UUID tenantId,
            UUID ownerId
    );
}
```

`JpaSpecificationExecutor` cho phép kết hợp các filter động bằng Specification. Các method tìm theo ID cũng mang tenant/owner scope ngay trong điều kiện repository, giúp tránh pattern nguy hiểm là lấy entity toàn cục bằng ID rồi mới kiểm tra quyền sau.

## 5. Lấy phạm vi truy cập từ principal đã xác thực

Tenant và owner scope phải được lấy từ danh tính đã xác thực. Ví dụ ứng dụng có principal:

```java
public record AppPrincipal(
        UUID userId,
        UUID tenantId,
        Set<String> authorities
) {
}
```

Mô hình phạm vi truy cập:

```java
public record AccessScope(
        UUID tenantId,
        UUID userId,
        boolean canReadAllInTenant
) {
}
```

Định nghĩa abstraction để service lấy scope:

```java
public interface AccessScopeProvider {
    AccessScope currentScope();
}
```

Implementation đọc SecurityContext:

```java
@Component
public class SecurityContextAccessScopeProvider
        implements AccessScopeProvider {

    @Override
    public AccessScope currentScope() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || !(authentication.getPrincipal() instanceof AppPrincipal p)) {
            throw new AccessDeniedException("Authenticated principal required");
        }

        if (p.tenantId() == null) {
            throw new AccessDeniedException("Tenant scope is missing");
        }

        boolean canReadAll =
                p.authorities().contains("employee:read:any");

        if (!canReadAll && p.userId() == null) {
            throw new AccessDeniedException("User scope is missing");
        }

        return new AccessScope(
                p.tenantId(),
                p.userId(),
                canReadAll
        );
    }
}
```

Đây là ví dụ principal tùy biến; nếu ứng dụng dùng JWT, OAuth2 hoặc một loại principal khác, implementation cần ánh xạ claim/authority đã được xác thực sang AccessScope. Không tin tenantId hoặc userId do client gửi trong request.

Một nguyên tắc quan trọng: nếu không thể xác định scope hợp lệ, từ chối truy cập. Không dùng giá trị null như tín hiệu “không giới hạn tenant”.

## 6. Predicate bắt buộc cho tenant và owner

Tạo Specification luôn áp dụng phạm vi truy cập:

```java
public final class EmployeeSpecifications {

    private EmployeeSpecifications() {
    }

    public static Specification<Employee> visibleTo(AccessScope scope) {
        if (scope == null || scope.tenantId() == null) {
            throw new IllegalArgumentException(
                    "A trusted tenant scope is required"
            );
        }

        if (!scope.canReadAllInTenant() && scope.userId() == null) {
            throw new IllegalArgumentException(
                    "A trusted user scope is required"
            );
        }

        return (root, query, cb) -> {
            Predicate tenantPredicate =
                    cb.equal(root.get("tenantId"), scope.tenantId());

            if (scope.canReadAllInTenant()) {
                return tenantPredicate;
            }

            Predicate ownerPredicate =
                    cb.equal(root.get("ownerId"), scope.userId());

            return cb.and(tenantPredicate, ownerPredicate);
        };
    }

    public static Specification<Employee> hasStatus(
            EmployeeStatus status
    ) {
        return (root, query, cb) -> status == null
                ? cb.conjunction()
                : cb.equal(root.get("status"), status);
    }
}
```

Với người dùng thông thường, predicate luôn tương đương:

```sql
WHERE tenant_id = :trustedTenantId
  AND owner_id = :trustedUserId
```

Với người có quyền đọc toàn tenant:

```sql
WHERE tenant_id = :trustedTenantId
```

`trustedTenantId` và `trustedUserId` đến từ AccessScope do server tạo. Chúng không đến từ query parameters.

Không đặt tenant predicate trong một nhánh filter tùy chọn. Nó là điều kiện bắt buộc cho mọi truy vấn dữ liệu của tenant.

## 7. Tạo filter tìm kiếm an toàn

Tiếp tục thêm Specification cho tên và khoảng thời gian:

```java
public static Specification<Employee> nameContains(String input) {
    return (root, query, cb) -> {
        if (input == null || input.isBlank()) {
            return cb.conjunction();
        }

        String normalized = input.trim().toLowerCase(Locale.ROOT);
        String escaped = normalized
                .replace("!", "!!")
                .replace("%", "!%")
                .replace("_", "!_");

        String pattern = "%" + escaped + "%";

        return cb.like(
                cb.lower(root.<String>get("name")),
                pattern,
                '!'
        );
    };
}

public static Specification<Employee> createdAtFrom(Instant from) {
    return (root, query, cb) -> from == null
            ? cb.conjunction()
            : cb.greaterThanOrEqualTo(
                    root.<Instant>get("createdAt"),
                    from
            );
}

public static Specification<Employee> createdAtBefore(Instant to) {
    return (root, query, cb) -> to == null
            ? cb.conjunction()
            : cb.lessThan(
                    root.<Instant>get("createdAt"),
                    to
            );
}
```

Các method này có thể nằm trong cùng class EmployeeSpecifications. Chúng trả về predicate luôn đúng khi filter tương ứng không được nhập; khi kết hợp AND, filter đó không thu hẹp tập kết quả.

### 7.1. Escape wildcard trong LIKE

Trong SQL LIKE, ký tự % đại diện cho chuỗi bất kỳ và _ đại diện cho một ký tự. Nếu nghiệp vụ muốn tìm chuỗi literal do người dùng nhập, phải escape các ký tự đó.

Ví dụ người dùng nhập `A_1%`. Nếu không escape, database có thể diễn giải _ và % như wildcard thay vì ký tự cần tìm.

Đoạn code dùng ! làm escape character:

- ! thành !!.
- % thành !%.
- _ thành !_.

Sau đó `cb.like(expression, pattern, '!')` yêu cầu Criteria API dùng ! làm ký tự escape. Cần kiểm thử semantics trên database/collation thực tế nếu tìm kiếm có yêu cầu Unicode hoặc dấu tiếng Việt đặc biệt.

Criteria API và Querydsl tạo query với bind parameter; không ghép trực tiếp input vào chuỗi SQL/JPQL.

## 8. Ghép filter người dùng với access scope

Service là nơi kết hợp filter tùy chọn với điều kiện quyền bắt buộc:

```java
@Service
@Transactional(readOnly = true)
public class EmployeeSearchService {

    private final EmployeeRepository repository;
    private final AccessScopeProvider scopeProvider;
    private final EmployeePageRequestFactory pageRequestFactory;

    public EmployeeSearchService(
            EmployeeRepository repository,
            AccessScopeProvider scopeProvider,
            EmployeePageRequestFactory pageRequestFactory
    ) {
        this.repository = repository;
        this.scopeProvider = scopeProvider;
        this.pageRequestFactory = pageRequestFactory;
    }

    @PreAuthorize("hasAuthority('employee:read')")
    public Page<EmployeeResponse> search(
            EmployeeFilter filter,
            int page,
            int size,
            EmployeeSortField sortBy,
            Sort.Direction direction
    ) {
        validateFilter(filter);

        AccessScope scope = scopeProvider.currentScope();

        Specification<Employee> specification =
                EmployeeSpecifications.visibleTo(scope)
                        .and(EmployeeSpecifications.nameContains(filter.name()))
                        .and(EmployeeSpecifications.hasStatus(filter.status()))
                        .and(EmployeeSpecifications.createdAtFrom(
                                filter.createdFrom()
                        ))
                        .and(EmployeeSpecifications.createdAtBefore(
                                filter.createdTo()
                        ));

        Pageable pageable = pageRequestFactory.create(
                page,
                size,
                sortBy,
                direction
        );

        return repository.findAll(specification, pageable)
                .map(EmployeeResponse::from);
    }

    private void validateFilter(EmployeeFilter filter) {
        if (filter.createdFrom() != null
                && filter.createdTo() != null
                && !filter.createdFrom().isBefore(filter.createdTo())) {
            throw new IllegalArgumentException(
                    "createdFrom must be earlier than createdTo"
            );
        }

        if (filter.createdFrom() != null
                && filter.createdTo() != null
                && Duration.between(
                        filter.createdFrom(),
                        filter.createdTo()
                ).compareTo(Duration.ofDays(366)) > 0) {
            throw new IllegalArgumentException(
                    "Search range must not exceed 366 days"
            );
        }
    }
}
```

`@PreAuthorize` kiểm tra quyền gọi use case ở mức chức năng. `visibleTo(scope)` kiểm soát hàng nào được phép đọc. Hai lớp có mục đích khác nhau và nên cùng được áp dụng.

Cấu hình method security:

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

Response DTO:

```java
public record EmployeeResponse(
        Long id,
        String name,
        EmployeeStatus status,
        Instant createdAt
) {
    public static EmployeeResponse from(Employee employee) {
        return new EmployeeResponse(
                employee.getId(),
                employee.getName(),
                employee.getStatus(),
                employee.getCreatedAt()
        );
    }
}
```

Không trả trực tiếp entity nếu API chỉ cần một số field. DTO giúp tránh vô tình lộ tenantId, ownerId, thông tin nội bộ hoặc association không dành cho caller.

## 9. Allowlist sort field

Không đưa trực tiếp chuỗi sort do client gửi vào query:

```java
Sort sort = Sort.by(request.getParameter("sort"));
```

Sort field không phải giá trị dữ liệu có thể bind như một parameter SQL thông thường. Nó ảnh hưởng đến cấu trúc ORDER BY. Vì vậy, cần ánh xạ từ một tập lựa chọn cố định sang property của entity.

Enum public API:

```java
public enum EmployeeSortField {
    NAME,
    CREATED_AT,
    STATUS
}
```

Factory ánh xạ:

```java
@Component
public class EmployeePageRequestFactory {

    private static final int MAX_PAGE_SIZE = 100;
    private static final long MAX_OFFSET = 100_000L;

    public Pageable create(
            int page,
            int size,
            EmployeeSortField sortBy,
            Sort.Direction direction
    ) {
        if (page < 0) {
            throw new IllegalArgumentException("page must be non-negative");
        }

        if (size < 1 || size > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException(
                    "size must be between 1 and " + MAX_PAGE_SIZE
            );
        }

        long offset = (long) page * size;
        if (offset > MAX_OFFSET) {
            throw new IllegalArgumentException(
                    "Requested offset is too deep; use cursor pagination"
            );
        }

        EmployeeSortField safeField =
                sortBy == null ? EmployeeSortField.CREATED_AT : sortBy;

        Sort.Direction safeDirection =
                direction == null ? Sort.Direction.DESC : direction;

        String property = switch (safeField) {
            case NAME -> "name";
            case CREATED_AT -> "createdAt";
            case STATUS -> "status";
        };

        Sort sort = Sort.by(
                new Sort.Order(safeDirection, property),
                Sort.Order.asc("id")
        );

        return PageRequest.of(page, size, sort);
    }
}
```

Client chỉ được chọn NAME, CREATED_AT hoặc STATUS. Server tự ánh xạ sang property hợp lệ. ID được thêm làm tie-breaker để tạo thứ tự ổn định khi nhiều hàng có cùng giá trị sort.

Không nhận chuỗi property tùy ý, tên association, biểu thức SQL hoặc hàm database từ client. Không dùng `JpaSort.unsafe` với input bên ngoài.

## 10. Controller và HTTP validation

Controller nhận filter DTO, page, size, sort enum và direction enum:

```java
@RestController
@RequestMapping("/api/employees")
@Validated
public class EmployeeController {

    private final EmployeeSearchService searchService;

    public EmployeeController(EmployeeSearchService searchService) {
        this.searchService = searchService;
    }

    @GetMapping
    public Page<EmployeeResponse> search(
            @Valid @ModelAttribute EmployeeFilterRequest filters,

            @RequestParam(defaultValue = "0")
            @Min(0)
            int page,

            @RequestParam(defaultValue = "20")
            @Min(1)
            @Max(100)
            int size,

            @RequestParam(defaultValue = "CREATED_AT")
            EmployeeSortField sortBy,

            @RequestParam(defaultValue = "DESC")
            Sort.Direction direction
    ) {
        return searchService.search(
                filters.toFilter(),
                page,
                size,
                sortBy,
                direction
        );
    }
}
```

Cần có Bean Validation provider, ví dụ dependency Spring Boot Validation starter. Khi method validation được bật, page âm hoặc size vượt giới hạn sẽ bị từ chối. Factory ở service vẫn kiểm tra lại vì service có thể được gọi từ nơi khác ngoài controller.

Giá trị sort không thuộc enum hoặc direction không hợp lệ sẽ không được chuyển đổi và request thường nhận HTTP 400. Đây là allowlist có kiểu, dễ kiểm tra và ít phụ thuộc cách database đặt tên cột.

### 10.1. Ví dụ request hợp lệ

```http
GET /api/employees?name=An&status=ACTIVE&page=0&size=20&sortBy=CREATED_AT&direction=DESC
```

Client có thể chọn filter và cách sắp xếp trong allowlist. Tenant và owner không xuất hiện trong request; server lấy scope từ principal.

### 10.2. Ví dụ request bị từ chối

```http
GET /api/employees?page=-1
GET /api/employees?size=100000
GET /api/employees?sortBy=tenantId
GET /api/employees?sortBy=createdAt desc, (select ...)
```

Các request này phải bị validation hoặc enum binding từ chối trước khi query được thực thi. Không sửa input sai thành sort mặc định một cách âm thầm nếu điều đó có thể che giấu lỗi hoặc làm client hiểu sai kết quả.

## 11. Page size, offset và chi phí count query

`Pageable` tiện lợi nhưng không tự giải quyết mọi vấn đề hiệu năng.

### 11.1. Giới hạn page size

Một page size quá lớn có thể:

- Tăng thời gian query và serialization.
- Tạo áp lực lên heap và garbage collection.
- Giữ connection lâu hơn.
- Tạo response lớn và tốn băng thông.
- Làm tăng chi phí hydrate entity và tải association.

Đặt default size nhỏ, ví dụ 20, và max size rõ ràng, ví dụ 100. Giá trị thực tế tùy endpoint và độ nặng của DTO.

Nếu dùng Spring Data web resolver trực tiếp với `Pageable`, có thể cấu hình giới hạn tại resolver hoặc property của Spring Boot. Tuy nhiên, nếu tự tạo PageRequest như ví dụ trên, phải tự enforce max size trong factory vì cấu hình resolver không kiểm soát PageRequest được tạo bằng code.

### 11.2. Giới hạn offset sâu

Page number lớn có thể tạo OFFSET rất sâu. Database thường vẫn phải tìm/đi qua nhiều hàng trước khi trả page tiếp theo. Ví dụ page 10.000 với size 100 tương ứng offset gần một triệu hàng.

Đặt giới hạn offset theo đặc điểm dữ liệu. Nếu người dùng cần đi sâu trong dataset lớn, chuyển sang keyset/cursor pagination thay vì cho phép offset không giới hạn.

### 11.3. Page và count query

`Page<T>` cung cấp `totalElements` và `totalPages`; Spring Data thường phải thực hiện count query để tính metadata này.

Count query cũng phải áp dụng cùng access scope. Nếu content query giới hạn tenant nhưng count query không giới hạn tenant, metadata có thể làm lộ quy mô dữ liệu ngoài quyền.

Nếu giao diện chỉ cần biết có trang kế tiếp hay không, dùng một query trả `Slice<T>` hoặc custom query phù hợp để tránh yêu cầu tổng số hàng. `JpaSpecificationExecutor.findAll(spec, pageable)` trả về Page; nếu cần Slice, có thể viết custom repository hoặc query riêng.

## 12. Keyset/cursor pagination cho dữ liệu lớn

Keyset pagination dùng giá trị của hàng cuối cùng trong trang trước để xác định vị trí tiếp theo. Với sort giảm dần theo createdAt rồi id:

```sql
SELECT id, name, status, created_at
FROM employees
WHERE tenant_id = :tenantId
  AND owner_id = :ownerId
  AND (
      created_at < :lastCreatedAt
      OR (
          created_at = :lastCreatedAt
          AND id < :lastId
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT :pageSizePlusOne
```

Predicate cursor so sánh từ khóa sắp xếp theo thứ tự từ trái sang phải. ID là tie-breaker để tránh bỏ sót hoặc lặp hàng có cùng timestamp.

Với người có quyền đọc toàn tenant, bỏ owner predicate theo scope server nhưng vẫn giữ tenant predicate bắt buộc. Không để client quyết định có bỏ owner/tenant filter hay không.

### 12.1. Cursor cần gắn với filter và access scope

Cursor không nên chỉ chứa lastId nếu thứ tự có nhiều field. Cursor có thể chứa:

- Giá trị cuối cùng của các field sort.
- Hướng sort.
- Phiên bản cursor.
- Dấu vết filter hoặc hash filter đang dùng.
- Hạn sử dụng và chữ ký chống sửa đổi.

Nếu cursor được encode thành Base64 thì đó chỉ là encoding, không phải bảo vệ. Có thể ký cursor bằng HMAC hoặc dùng token opaque được lưu server-side. Khi nhận cursor, server phải xác thực chữ ký, kiểm tra version và tiếp tục áp dụng access scope từ principal hiện tại.

Không lấy tenantId trong cursor làm căn cứ cấp quyền. Nếu cursor được tạo bởi user A rồi dùng bởi user B, scope của user B vẫn phải được áp dụng; tốt hơn là ràng buộc cursor với tenant/user scope và filter hash để tránh tái sử dụng sai ngữ cảnh.

## 13. Kiểm soát quyền ở danh sách, chi tiết và thao tác ghi

Bảo vệ endpoint danh sách chưa đủ. Cùng một quy tắc phải được áp dụng cho:

- Tìm kiếm và phân trang.
- Count và exists.
- Xem chi tiết theo ID.
- Cập nhật và xóa.
- Export CSV/Excel/PDF.
- Báo cáo, dashboard và thống kê.
- Background job chạy thay mặt tenant/user.
- Cache chứa kết quả tìm kiếm.

Ví dụ tìm chi tiết theo scope:

```java
@Service
@Transactional(readOnly = true)
public class EmployeeReadService {

    private final EmployeeRepository repository;
    private final AccessScopeProvider scopeProvider;

    public EmployeeReadService(
            EmployeeRepository repository,
            AccessScopeProvider scopeProvider
    ) {
        this.repository = repository;
        this.scopeProvider = scopeProvider;
    }

    @PreAuthorize("hasAuthority('employee:read')")
    public EmployeeResponse getVisible(Long id) {
        AccessScope scope = scopeProvider.currentScope();

        Employee employee = scope.canReadAllInTenant()
                ? repository.findByIdAndTenantId(
                        id,
                        scope.tenantId()
                ).orElseThrow(
                        () -> new ResponseStatusException(HttpStatus.NOT_FOUND)
                )
                : repository.findByIdAndTenantIdAndOwnerId(
                        id,
                        scope.tenantId(),
                        scope.userId()
                ).orElseThrow(
                        () -> new ResponseStatusException(HttpStatus.NOT_FOUND)
                );

        return EmployeeResponse.from(employee);
    }
}
```

Trả 404 cho ID không tồn tại hoặc không thuộc phạm vi caller có thể tránh tiết lộ sự tồn tại của bản ghi ngoài quyền. Một số hệ thống chọn 403; điều quan trọng là chính sách phải nhất quán và không để lộ dữ liệu nhạy cảm.

Với update/delete, thực hiện load có scope trong transaction rồi thay đổi entity managed. Không gọi `findById(id)` toàn cục rồi mới kiểm tra tenant sau khi dữ liệu đã được nạp. Nếu có optimistic locking, giữ `@Version` để xử lý cập nhật đồng thời.

### 13.1. Count và exists cũng là dữ liệu

Các API như `/employees/count`, `/employees/exists?email=...` hoặc thống kê theo trạng thái có thể tiết lộ dữ liệu dù không trả entity.

Mọi count/exists phải ghép scope:

```java
Specification<Employee> scoped =
        EmployeeSpecifications.visibleTo(scope)
                .and(EmployeeSpecifications.hasStatus(status));

long count = repository.count(scoped);
```

Không dùng `repository.count()` hoặc `repository.existsById(id)` cho dữ liệu tenant-scoped nếu không có predicate/derived method bảo đảm cùng phạm vi quyền.

## 14. RBAC, row-level authorization và default deny

Có thể phân biệt hai quyết định:

- RBAC: user có quyền gọi chức năng nào? Ví dụ `employee:read`, `employee:update`.
- Row-level/attribute-based authorization: user được đọc hàng nào? Ví dụ cùng tenant và owner là chính user, hoặc có quyền đọc toàn tenant.

Ví dụ:

| Vai trò/quyền | Phạm vi |
|---|---|
| employee:read | Được gọi API đọc nhân viên trong phạm vi cá nhân |
| employee:read:any | Được đọc tất cả nhân viên trong tenant hiện tại |
| employee:update | Được yêu cầu cập nhật; vẫn phải kiểm tra row scope |
| system:admin | Có thể có phạm vi quản trị riêng, cần định nghĩa rõ |

Không suy luận rằng người có quyền `employee:read:any` được đọc tất cả tenant. Quyền này trong ví dụ chỉ mở rộng owner scope bên trong tenant đang xác thực.

Nguyên tắc default deny:

- Không có principal hợp lệ: từ chối.
- Thiếu tenant scope: từ chối.
- User thường thiếu user ID: từ chối.
- Không có authority endpoint: từ chối.
- Không tìm thấy hàng trong scope: không trả dữ liệu.
- Không rõ một role có được bỏ tenant restriction hay không: giữ tenant restriction cho tới khi có chính sách đặc biệt được định nghĩa và kiểm thử.

Không dùng `@PostFilter` trên một Page lớn như cơ chế chính để bảo vệ dữ liệu. Lọc sau khi query đã chạy có thể làm sai total count, tải dữ liệu không được phép vào memory và tạo side channel. Hãy đưa predicate vào query trước khi dữ liệu được trả về.

## 15. Chống SQL injection và sort injection

Criteria API, JPQL parameter binding và Querydsl giúp bind giá trị filter an toàn. Tuy nhiên, không có nghĩa mọi chuỗi client gửi đều an toàn ở mọi vị trí.

Không ghép trực tiếp input vào JPQL:

```java
String jpql = "select e from Employee e order by " + requestSort;
```

Không nối chuỗi để tạo điều kiện WHERE:

```java
String sql = "where name like '%" + userInput + "%'";
```

Dùng Criteria/Specification hoặc bind parameter. Với những phần query không thể bind như property name, direction, function hoặc column, dùng allowlist server-side.

Không cho client truyền:

- Tên property tùy ý để sort.
- JPQL fragment hoặc SQL expression.
- Tên function, join path hoặc alias.
- Tên entity/table/column.
- `JpaSort.unsafe` expression.

Enum sort field và switch mapping trong bài là cách đơn giản để giới hạn cấu trúc query.

## 16. Chống enumeration, abuse và rò rỉ qua response

Một endpoint tìm kiếm có thể bị lạm dụng dù filter và SQL đã an toàn.

Các biện pháp bổ sung:

**Giới hạn truy vấn rộng.** Nếu tenant có hàng triệu bản ghi, yêu cầu ít nhất một filter có ý nghĩa hoặc khoảng thời gian giới hạn cho các vai trò có phạm vi rộng.

**Rate limit.** Giới hạn tần suất request theo user, tenant, client hoặc API key. Tăng cường giới hạn với export và truy vấn tốn kém.

**Giới hạn response.** Page size tối đa, giới hạn tổng số hàng export và xử lý export lớn bằng job có quyền kiểm soát.

**Giới hạn thời gian.** Có query timeout phù hợp, cancellation và giám sát slow query.

**Ẩn field nhạy cảm.** DTO chỉ trả field cần thiết; không serialize entity graph tùy tiện.

**Thông báo lỗi thống nhất.** Không trả SQL, table name, tenant existence hoặc stack trace cho client. Ghi chi tiết vào log nội bộ có kiểm soát.

**Cache theo scope.** Cache key phải bao gồm tenant, user/role scope và filter/sort/page. Không dùng cùng cache key cho hai tenant khác nhau. Cẩn thận với shared cache và invalidation sau khi quyền thay đổi.

**Log có chọn lọc.** Tránh log PII hoặc filter nhạy cảm nguyên văn. Có thể log request ID, thời gian, page size, sort field, scope identifier đã mask và kết quả tổng quát theo chính sách.

## 17. Kiểm thử filter và phạm vi quyền

Kiểm thử phải chứng minh rằng dữ liệu ngoài scope không xuất hiện trong content và cũng không xuất hiện trong metadata.

Ví dụ repository integration test:

```java
@DataJpaTest
class EmployeeSearchRepositoryTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private EmployeeRepository repository;

    @Test
    void restrictsRowsAndCountToCurrentTenantAndOwner() {
        UUID tenantA = UUID.randomUUID();
        UUID tenantB = UUID.randomUUID();
        UUID userA = UUID.randomUUID();
        UUID userB = UUID.randomUUID();

        entityManager.persist(new Employee(
                tenantA, userA, "An", EmployeeStatus.ACTIVE,
                Instant.parse("2026-01-10T00:00:00Z")
        ));
        entityManager.persist(new Employee(
                tenantA, userB, "Binh", EmployeeStatus.ACTIVE,
                Instant.parse("2026-01-11T00:00:00Z")
        ));
        entityManager.persist(new Employee(
                tenantB, userA, "Chi", EmployeeStatus.ACTIVE,
                Instant.parse("2026-01-12T00:00:00Z")
        ));

        entityManager.flush();
        entityManager.clear();

        AccessScope scope =
                new AccessScope(tenantA, userA, false);

        Specification<Employee> specification =
                EmployeeSpecifications.visibleTo(scope)
                        .and(EmployeeSpecifications.hasStatus(
                                EmployeeStatus.ACTIVE
                        ));

        Page<Employee> page = repository.findAll(
                specification,
                PageRequest.of(
                        0,
                        10,
                        Sort.by(Sort.Direction.ASC, "id")
                )
        );

        assertThat(page.getContent())
                .extracting(Employee::getName)
                .containsExactly("An");

        assertThat(page.getTotalElements()).isEqualTo(1);
        assertThat(page.getTotalPages()).isEqualTo(1);
    }
}
```

Test này tạo ba hàng: cùng tenant/cùng owner, cùng tenant/owner khác và tenant khác. Kết quả chỉ được chứa hàng đầu tiên. Quan trọng hơn, totalElements cũng phải là 1, không phải 2 hoặc 3.

### 17.1. Kiểm thử quyền đọc toàn tenant

Thêm test với:

```java
AccessScope tenantAdmin =
        new AccessScope(tenantA, adminUserId, true);

Specification<Employee> specification =
        EmployeeSpecifications.visibleTo(tenantAdmin);

assertThat(repository.count(specification)).isEqualTo(2);
```

Quyền đọc toàn tenant chỉ trả hai hàng của tenantA, không bao gồm tenantB. Bài test này ngăn việc nhầm quyền tenant admin với quyền truy cập toàn hệ thống.

### 17.2. Kiểm thử HTTP validation và security

Ngoài repository test, dùng MockMvc hoặc integration test phù hợp để kiểm tra:

- Không đăng nhập: 401 hoặc response theo security configuration.
- Không có authority đọc: 403.
- sort field ngoài enum: 400.
- page âm: 400.
- size bằng 0 hoặc vượt max: 400.
- offset vượt ngưỡng: 400.
- createdFrom lớn hơn createdTo: 400.
- User A không xem được ID của user B.
- Tenant A không xem được ID của tenant B.
- Count, export và endpoint chi tiết cũng áp dụng cùng scope.
- Request gửi tenantId/ownerId giả không thay đổi phạm vi quyền.

Không chỉ test controller trả status code. Hãy kiểm tra dữ liệu thực tế và metadata của response.

## 18. Index và execution plan

Index cần hỗ trợ điều kiện scope và sort thường dùng. Nếu query luôn lọc tenant, sau đó lọc owner và sắp xếp theo createdAt/id, index tổng hợp có thể được cân nhắc:

```sql
CREATE INDEX ix_employee_tenant_owner_created_id
ON employees (tenant_id, owner_id, created_at, id);
```

Với truy vấn tenant admin không có owner predicate, một index khác có thể hữu ích:

```sql
CREATE INDEX ix_employee_tenant_created_id
ON employees (tenant_id, created_at, id);
```

Hai câu DDL là ví dụ SQL phổ biến; cú pháp và khả năng index direction/covering khác nhau theo database. Không tạo index chỉ vì thấy một cột trong WHERE. Hãy xem:

- Selectivity/cardinality của tenantId, ownerId và status.
- Thứ tự cột trong composite index.
- Sort direction và khả năng database dùng index cho ORDER BY.
- LIKE có wildcard đầu hay không.
- Count query và filter combination thường gặp.
- Chi phí ghi tăng lên do có quá nhiều index.

Dùng EXPLAIN hoặc EXPLAIN ANALYZE trên database đích. Test với dữ liệu có quy mô và phân bố gần production; một bảng test nhỏ có thể khiến optimizer chọn plan khác.

## 19. Database row-level security như lớp bảo vệ bổ sung

Một số database hỗ trợ Row-Level Security (RLS), ví dụ PostgreSQL. RLS có thể bổ sung một lớp kiểm soát ở database để ngay cả query thiếu tenant predicate cũng bị giới hạn theo session policy.

RLS không thay thế authorization trong ứng dụng. Cần thiết kế cẩn thận:

- Thiết lập tenant/session context từ server đã xác thực.
- Đảm bảo connection pool không để session variable của request trước rò sang request sau.
- Đặt/reset context trong transaction hoặc cơ chế an toàn tương ứng.
- Kiểm thử policy với application database user thực tế.
- Không cấp quyền bypass RLS cho user ứng dụng thông thường.
- Kiểm tra background jobs, migration user và admin connection riêng.

Nếu ứng dụng dùng connection pooling, trạng thái session phải được quản lý chính xác. Một session variable không được reset có thể khiến request tiếp theo dùng nhầm tenant context. RLS nên được triển khai như defense in depth cùng với scope predicate ở service/repository.

## 20. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| User nhìn thấy bản ghi tenant khác | Query thiếu tenant predicate | Ghép scope bắt buộc từ SecurityContext |
| Danh sách đúng nhưng totalElements sai | Count query không áp dụng scope hoặc join làm nhân bản hàng | Kiểm thử count cùng predicate, xử lý DISTINCT khi cần |
| User đổi ownerId để đọc dữ liệu người khác | Lấy scope từ request | Lấy owner/tenant từ principal |
| API chấp nhận sort field lạ | Dùng chuỗi sort trực tiếp từ client | Dùng enum allowlist và switch mapping |
| Page size quá lớn | Không giới hạn size ở server | Enforce max trong resolver và service factory |
| Page sâu làm query chậm | OFFSET lớn | Giới hạn offset, chuyển sang keyset/cursor |
| Search wildcard trả quá nhiều hàng | Không escape % và _ theo semantics literal | Escape wildcard và dùng escape character |
| Filter sai bị bỏ qua âm thầm | Không validate input | Trả 400 với lỗi rõ ràng |
| API detail bị IDOR | findById toàn cục rồi kiểm tra quyền không đầy đủ | Query theo ID + tenant + owner scope |
| Export lộ nhiều dữ liệu hơn danh sách | Export dùng query khác không có scope | Tái sử dụng cùng authorization policy |
| Cache trả dữ liệu tenant khác | Cache key thiếu tenant/user scope | Thêm scope vào key và kiểm soát invalidation |
| @PostFilter làm chậm và lộ dữ liệu trong memory | Lọc sau khi query | Đưa predicate vào SQL trước khi đọc |
| Query an toàn nhưng vẫn quá tải | Thiếu rate limit, timeout và giới hạn khoảng tìm kiếm | Áp dụng resource controls theo endpoint |
| Test chỉ kiểm tra content | Không kiểm tra count/totalPages hoặc tenant khác | Tạo fixture đa tenant và assert cả metadata |

## 21. Checklist trước khi đưa API tìm kiếm vào production

- [ ] Dùng search DTO riêng, không bind entity trực tiếp.
- [ ] DTO chỉ chứa filter được phép.
- [ ] Validate độ dài, enum, khoảng thời gian và trạng thái null/blank.
- [ ] Tenant/owner scope lấy từ principal đã xác thực.
- [ ] Scope bắt buộc được ghép vào mọi query.
- [ ] RBAC endpoint permission và row-level authorization được kiểm tra riêng.
- [ ] Detail/update/delete cũng query theo scope.
- [ ] Count/exists/export/report áp dụng cùng phạm vi.
- [ ] Response dùng DTO, không serialize entity tùy tiện.
- [ ] Sort field và direction nằm trong allowlist.
- [ ] Không nhận SQL/JPQL fragment hoặc JpaSort.unsafe từ client.
- [ ] Page size có default và max rõ ràng.
- [ ] Offset sâu bị giới hạn hoặc chuyển sang cursor pagination.
- [ ] Sort có tie-breaker duy nhất.
- [ ] Cursor được xác thực và gắn với filter/scope phù hợp.
- [ ] Query LIKE escape wildcard theo semantics nghiệp vụ.
- [ ] Rate limit, query timeout và giới hạn export được cấu hình.
- [ ] Cache key chứa tenant/user/role scope.
- [ ] Integration test chứng minh content và count không vượt scope.
- [ ] Test HTTP cho authentication, authority, sort, page và size.
- [ ] Index được xác nhận bằng execution plan trên database đích.
- [ ] RLS nếu có được dùng như defense in depth và quản lý session pool an toàn.

## Kết luận

Một bộ lọc an toàn cần kết hợp validation, giới hạn tài nguyên và authorization ở cấp bản ghi. Dùng DTO để giới hạn field client có thể điều khiển; dùng enum allowlist cho sort; giới hạn page size và offset; thêm tie-breaker duy nhất để thứ tự ổn định. Với dữ liệu lớn, keyset pagination giúp tránh OFFSET sâu.

Quan trọng nhất, tenant/owner scope phải đến từ principal đã xác thực và được ghép vào predicate ở server cho mọi thao tác đọc. Danh sách, count, exists, detail, update, delete, export và cache đều phải tuân thủ cùng chính sách. Hãy kiểm thử bằng fixture có nhiều tenant và owner, xác nhận cả content lẫn totalElements, rồi kiểm tra execution plan và giới hạn request trên database tương ứng production.

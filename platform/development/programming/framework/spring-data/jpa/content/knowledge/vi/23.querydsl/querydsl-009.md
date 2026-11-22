# Kiểm soát thuộc tính được công khai khi nhận predicate từ web

## Mục tiêu

Sau bài này, bạn có thể nhận Querydsl predicate từ query parameter của HTTP request bằng `@QuerydslPredicate`; giới hạn những thuộc tính được phép bind bằng `QuerydslBindings`; tùy chỉnh cách so khớp qua `QuerydslBinderCustomizer`; kết hợp predicate do client gửi với điều kiện bảo mật do server áp đặt; và kiểm thử bộ lọc, phân trang, sort cùng dữ liệu nhạy cảm.

Các ví dụ dùng Java 17+, Spring Boot 3+, Spring Data JPA và Querydsl tương thích Jakarta Persistence. Querydsl cần annotation processor để sinh các lớp metamodel như `QUser`. Hãy dùng artifact và phiên bản Querydsl tương thích với phiên bản Spring Data/Boot của dự án; với Boot 3, cần bản Jakarta thay vì artifact cũ phụ thuộc `javax.persistence`.

## 1. Vì sao phải kiểm soát predicate nhận từ web?

Spring Data hỗ trợ chuyển query parameter thành Querydsl `Predicate`. Cách này tiện cho màn hình tìm kiếm có nhiều bộ lọc, nhưng entity thường chứa cả thuộc tính nội bộ như `tenantId`, `passwordHash`, cờ xóa mềm, quyền hoặc dữ liệu vận hành.

Nếu để mọi thuộc tính của entity có thể được bind từ request, client có thể thử lọc theo các trường không thuộc hợp đồng API. Điều đó có thể làm lộ cấu trúc nội bộ, tạo truy vấn nặng, hoặc khiến ứng dụng vô tình cho phép client điều khiển một phần dữ liệu đáng lẽ phải được xác định từ danh tính đã xác thực.

Nguyên tắc thiết kế:

- Chỉ công khai các filter mà use case thực sự cần.
- Dùng allowlist cho thuộc tính được bind; không dựa vào việc nhớ exclude từng field nhạy cảm.
- Giữ điều kiện phân quyền, tenant và phạm vi dữ liệu ở server; luôn kết hợp chúng với predicate client gửi.
- Trả DTO/projection thay vì entity persistence.
- Giới hạn page size, sort và độ phức tạp của filter.

`@QuerydslPredicate` là cơ chế chuyển request thành điều kiện truy vấn. Nó không phải lớp phân quyền và không thay thế authorization.

## 2. Điều kiện cần để dùng Querydsl web support

Spring Data JPA tích hợp với Querydsl thông qua các thành phần chính:

- Querydsl JPA và annotation processor tương thích Jakarta Persistence.
- Các lớp Q được sinh từ entity, ví dụ `QUser` cho entity `User`.
- Repository kế thừa `QuerydslPredicateExecutor<T>` để thực thi predicate.
- Spring Data web support để giải quyết tham số `@QuerydslPredicate` trong controller.

Trong Spring Boot, web support thường được cấu hình tự động cùng Spring Data web auto-configuration. Với ứng dụng Spring không dùng Boot auto-configuration, có thể bật bằng `@EnableSpringDataWebSupport`.

Ví dụ cấu hình annotation processing ở mức khái niệm:

```text
querydsl-jpa: Jakarta-compatible artifact
querydsl-apt: Jakarta-compatible annotation processor
annotation processing: enabled at compile time
```

Không trộn Querydsl artifact dựa trên `javax.persistence` với entity Jakarta (`jakarta.persistence`). Nếu lớp `QUser` không được sinh, kiểm tra annotation processor và generated-sources directory trước khi xem repository code.

## 3. Entity mẫu và các trường nội bộ

Entity ví dụ có cả trường phục vụ tìm kiếm lẫn trường chỉ dùng nội bộ:

```java
package com.example.learning.user;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "users")
public class User {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(nullable = false, unique = true)
    private String username;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @Column(nullable = false)
    private String email;

    @Column(name = "password_hash", nullable = false)
    private String passwordHash;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private UserStatus status;

    @Column(nullable = false)
    private Boolean active;

    protected User() {
    }

    public User(Long tenantId, String username, String displayName,
                String email, String passwordHash,
                UserStatus status, Boolean active) {
        this.tenantId = tenantId;
        this.username = username;
        this.displayName = displayName;
        this.email = email;
        this.passwordHash = passwordHash;
        this.status = status;
        this.active = active;
    }

    public Long getId() { return id; }
    public Long getTenantId() { return tenantId; }
    public String getUsername() { return username; }
    public String getDisplayName() { return displayName; }
    public String getEmail() { return email; }
    public UserStatus getStatus() { return status; }
    public Boolean getActive() { return active; }
}
```

```java
package com.example.learning.user;

public enum UserStatus {
    NEW,
    ACTIVE,
    SUSPENDED
}
```

`tenantId` và `passwordHash` là ví dụ về dữ liệu không được client điều khiển qua filter công khai. `email` cũng có thể cần giữ kín tùy hợp đồng API; không đưa một field vào allowlist chỉ vì nó tồn tại trong entity.

## 4. Nhận predicate trong controller

Spring Data cung cấp annotation `@QuerydslPredicate` để chuyển query parameter thành Querydsl predicate:

```java
package com.example.learning.user;

import com.querydsl.core.types.Predicate;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.web.querydsl.QuerydslPredicate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/users")
public class UserController {
    private final UserSearchService searchService;

    public UserController(UserSearchService searchService) {
        this.searchService = searchService;
    }

    @GetMapping
    public Page<UserSummary> search(
            @QuerydslPredicate(root = User.class) Predicate predicate,
            @PageableDefault(size = 20, sort = "username") Pageable pageable) {
        return searchService.search(predicate, pageable);
    }
}
```

Ví dụ request:

```http
GET /users?username=ada&status=ACTIVE&active=true&page=0&size=20&sort=username,asc
```

Với cấu hình binder ở phần tiếp theo, `username` có thể được so khớp contains-ignore-case, còn `status` và `active` dùng phép so sánh phù hợp với kiểu dữ liệu. Các query parameter `tenantId` và `passwordHash` sẽ không được đưa vào predicate.

Trong ứng dụng không dùng Spring Boot auto-configuration, cần bật Spring Data web support bằng `@EnableSpringDataWebSupport`. `@QuerydslPredicate` chỉ tạo predicate từ request; repository executor hoặc service vẫn phải thực thi nó.

## 5. Allowlist bằng QuerydslBinderCustomizer

Cách quan trọng nhất để kiểm soát thuộc tính công khai là loại trừ mọi property trước, rồi chỉ thêm những path được phép:

```java
package com.example.learning.user;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;
import org.springframework.data.querydsl.binding.QuerydslBinderCustomizer;
import org.springframework.data.querydsl.binding.QuerydslBindings;

public interface UserRepository
        extends JpaRepository<User, Long>,
                QuerydslPredicateExecutor<User>,
                QuerydslBinderCustomizer<QUser> {

    @Override
    default void customize(QuerydslBindings bindings, QUser user) {
        bindings.excludeUnlistedProperties(true);

        bindings.including(
            user.username,
            user.displayName,
            user.status,
            user.active
        );

        bindings.bind(user.username)
            .first((path, value) -> path.containsIgnoreCase(value.trim()));

        bindings.bind(user.displayName)
            .first((path, value) -> path.containsIgnoreCase(value.trim()));

        bindings.excluding(user.tenantId, user.passwordHash);
    }
}
```

Ý nghĩa:

- `excludeUnlistedProperties(true)` đặt chế độ mặc định là không cho bind property chưa được công khai.
- `including(...)` tạo allowlist các field mà API tìm kiếm hỗ trợ.
- `bind(...).first(...)` định nghĩa phép so khớp cho từng path.
- `excluding(...)` nêu rõ các field nhạy cảm cần bị loại; trong ví dụ allowlist đã chặn chúng, nhưng exclude tường minh cũng giúp người đọc nhận ra ranh giới bảo mật.

Spring Data web support có thể sử dụng `QuerydslBinderCustomizer` được khai báo trên repository tương ứng với root entity. Nhờ đó controller không cần tự xây dựng lại các binding rule.

Không dùng `bindings.bind(String.class)` để mở một quy tắc toàn cục cho mọi chuỗi nếu entity có nhiều trường nội bộ. Binding theo từng path giúp API chỉ công khai chính xác những field được chọn.

## 6. Tùy chỉnh phép so khớp và nhiều giá trị

Binding mặc định có thể không đúng với trải nghiệm tìm kiếm mong muốn. Với username, tìm chính xác có thể quá chặt; contains-ignore-case phù hợp hơn cho ô tìm kiếm tên đăng nhập:

```java
bindings.bind(user.username)
    .first((path, value) -> path.containsIgnoreCase(value.trim()));
```

Với status, phép so sánh equality thường rõ ràng:

```java
bindings.bind(user.status)
    .first((path, value) -> path.eq(value));
```

Nếu API muốn hỗ trợ nhiều status trong một request, có thể định nghĩa binding nhận collection:

```java
import java.util.Optional;

bindings.bind(user.status)
    .all((path, values) -> Optional.of(path.in(values)));
```

Ví dụ request có thể truyền nhiều giá trị `status` theo cách lặp query parameter:

```http
GET /users?status=ACTIVE&status=NEW
```

Binding `.all(...)` biến tập giá trị thành điều kiện `IN`. Hãy kiểm thử cách client gửi nhiều giá trị và xác nhận conversion enum hoạt động theo phiên bản Spring Data/Querydsl đang dùng. Với một giá trị đơn, collection vẫn tạo `IN` một phần tử; nếu muốn equality cho một giá trị và IN cho nhiều giá trị, triển khai rule rõ ràng và kiểm tra trường hợp collection rỗng.

Không nhận chuỗi filter tùy ý rồi chuyển thẳng thành Querydsl expression. Client chỉ nên chọn từ các thuộc tính và phép so khớp đã được server định nghĩa.

## 7. Predicate từ client không được quyết định phạm vi phân quyền

Allowlist ngăn client lọc theo field không được công khai, nhưng nó không bảo đảm user chỉ thấy dữ liệu của chính họ. Phạm vi tenant, owner, organization hoặc quyền truy cập phải được tạo từ security context phía server.

Ví dụ service luôn thêm điều kiện tenant:

```java
package com.example.learning.user;

import com.querydsl.core.BooleanBuilder;
import com.querydsl.core.types.Predicate;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UserSearchService {
    private final UserRepository users;
    private final TenantContext tenantContext;

    public UserSearchService(UserRepository users, TenantContext tenantContext) {
        this.users = users;
        this.tenantContext = tenantContext;
    }

    @Transactional(readOnly = true)
    public Page<UserSummary> search(Predicate clientPredicate, Pageable pageable) {
        BooleanBuilder scoped = new BooleanBuilder(
            QUser.user.tenantId.eq(tenantContext.requiredTenantId())
        );

        if (clientPredicate != null) {
            scoped.and(clientPredicate);
        }

        return users.findAll(scoped, pageable).map(UserSummary::from);
    }
}
```

`TenantContext` là abstraction của ứng dụng để lấy tenant từ principal hoặc security context đã xác thực:

```java
package com.example.learning.user;

public interface TenantContext {
    long requiredTenantId();
}
```

Điều kiện tenant được tạo từ server và kết hợp bằng AND với predicate client gửi. Request có thêm `tenantId=...` cũng không thể thay thế điều kiện này vì `tenantId` không nằm trong allowlist; ngay cả khi ai đó vô tình thêm binding sau này, điều kiện server vẫn phải được giữ.

Không lấy tenant ID hoặc owner ID từ query parameter để quyết định quyền truy cập. Nếu endpoint phục vụ admin nhiều tenant, hãy dùng authorization policy riêng, kiểm tra role/permission ở server và ghi log theo yêu cầu bảo mật.

## 8. Trả DTO thay vì entity

Không nên trả trực tiếp entity `User` từ controller chỉ vì repository đã trả entity. Entity có thể chứa field nội bộ, quan hệ lazy hoặc cấu trúc persistence không phù hợp với API.

DTO response:

```java
package com.example.learning.user;

public record UserSummary(
    Long id,
    String username,
    String displayName,
    UserStatus status,
    Boolean active
) {
    public static UserSummary from(User user) {
        return new UserSummary(
            user.getId(),
            user.getUsername(),
            user.getDisplayName(),
            user.getStatus(),
            user.getActive()
        );
    }
}
```

DTO chỉ chứa những trường endpoint được phép trả về. `passwordHash`, `tenantId` và các association nội bộ không xuất hiện trong response. Nếu query cần hiệu năng đọc cao, có thể cân nhắc projection/DTO query trực tiếp thay vì load entity rồi map; dù dùng cách nào, allowlist response vẫn cần được kiểm soát.

## 9. Kiểm soát Pageable và Sort riêng với predicate

`@QuerydslPredicate` kiểm soát điều kiện lọc. `Pageable` và `Sort` là cơ chế web binding riêng, vì vậy allowlist của `QuerydslBindings` không tự giới hạn cột sort.

Giới hạn page size trong Spring Boot:

```properties
spring.data.web.pageable.default-page-size=20
spring.data.web.pageable.max-page-size=100
```

Chỉ cho phép sort theo các property đã chọn. Ví dụ kiểm tra ở service hoặc controller:

```java
private static final Set<String> ALLOWED_SORTS = Set.of(
    "username", "displayName", "status"
);

private static void validateSort(Pageable pageable) {
    boolean invalid = pageable.getSort().stream()
        .anyMatch(order -> !ALLOWED_SORTS.contains(order.getProperty()));

    if (invalid) {
        throw new IllegalArgumentException("Unsupported sort property");
    }
}
```

Trong ứng dụng thực tế, chuyển lỗi validation này thành HTTP 400 bằng exception handler. Không cho phép sort theo `passwordHash`, `tenantId` hoặc association tùy ý chỉ vì entity có property đó.

Page size quá lớn có thể tạo truy vấn tốn tài nguyên và response rất nặng. Hãy đặt giới hạn phù hợp với use case, database và giới hạn tải của hệ thống.

## 10. Hành vi với property không được allowlist

Khi `excludeUnlistedProperties(true)` được bật, property không được liệt kê không được bind vào predicate. Tùy cách argument resolver và cấu hình validation, query parameter không được hỗ trợ có thể bị bỏ qua thay vì tự động trả HTTP 400.

Vì vậy, nếu API yêu cầu từ chối mọi parameter lạ, cần thêm validation ở tầng HTTP: so sánh tên query parameter nhận được với danh sách cho phép, trả 400 cho key không hợp lệ và kiểm thử hành vi đó. Không giả định `excludeUnlistedProperties(true)` tự động là cơ chế reject request.

Ví dụ phân loại:

| Query parameter | Chính sách |
| --- | --- |
| `username` | Cho phép, contains-ignore-case |
| `displayName` | Cho phép, contains-ignore-case |
| `status` | Cho phép, equality hoặc IN theo binding |
| `active` | Cho phép, equality boolean |
| `tenantId` | Không bind; tenant do server xác định |
| `passwordHash` | Không bind; dữ liệu nhạy cảm |
| `email` | Không bind nếu chưa được duyệt trong hợp đồng API |
| `sort=passwordHash` | Từ chối bởi sort allowlist |

## 11. Hiệu năng và giới hạn truy vấn

Public filter cũng là bề mặt tiêu thụ tài nguyên. Một số lưu ý:

- `containsIgnoreCase` thường tạo tìm kiếm kiểu `%value%`; index B-tree thông thường có thể không hỗ trợ hiệu quả trên nhiều database.
- Giới hạn độ dài chuỗi filter và số lượng giá trị lặp cho các field dạng collection.
- Không expose filter trên association sâu hoặc collection lớn nếu chưa đánh giá join và cardinality.
- Kiểm tra execution plan, index và count query khi endpoint trả `Page<T>`.
- Dùng `Slice<T>` hoặc giới hạn số kết quả nếu giao diện không cần tổng số bản ghi.
- Tránh để client điều khiển hàng chục filter cùng lúc nếu truy vấn kết hợp có thể tạo plan rất nặng.

Với tìm kiếm tên, có thể chọn `startsWithIgnoreCase` thay cho `containsIgnoreCase` nếu trải nghiệm sản phẩm cho phép và muốn tận dụng index tốt hơn. Đây là quyết định cần đo trên database thật, không phải quy tắc áp dụng cho mọi hệ quản trị.

## 12. Kiểm thử web binding và ranh giới bảo mật

Kiểm thử nên bao gồm cả cách bind filter và cách service áp dụng phạm vi dữ liệu:

1. Request có `username=ada` chỉ trả user phù hợp với phép contains-ignore-case.
2. Request có `status=ACTIVE` chỉ trả status được chọn.
3. Query parameter `passwordHash` không tạo predicate và không xuất hiện trong response.
4. Query parameter `tenantId` không thể chuyển tenant của request.
5. User thuộc tenant khác không xuất hiện dù client gửi filter hợp lệ.
6. Sort ngoài allowlist bị từ chối; page size vượt giới hạn bị giới hạn hoặc trả lỗi theo hợp đồng API.
7. Giá trị enum hoặc boolean không hợp lệ được xử lý nhất quán, thường là HTTP 400.
8. Nhiều giá trị lặp chỉ hoạt động theo semantics mà binder đã định nghĩa.

Ví dụ khung integration test với MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class UserSearchWebTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void doesNotExposeInternalFields() throws Exception {
        mvc.perform(get("/users")
                .param("username", "ada")
                .param("passwordHash", "guess")
                .param("page", "0")
                .param("size", "20"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$..passwordHash").doesNotExist())
            .andExpect(jsonPath("$..tenantId").doesNotExist());
    }
}
```

Đây là khung test; project cần seed dữ liệu, cấu hình authentication/tenant context và import các static matcher của MockMvc/JSONPath. Bổ sung assertion về `totalElements` hoặc nội dung trang để xác nhận parameter nội bộ không ảnh hưởng tới kết quả. Test bảo mật tenant phải có fixture thuộc ít nhất hai tenant và xác nhận response chỉ chứa tenant của principal hiện tại.

Không chỉ kiểm thử repository trực tiếp với `Predicate`; cần có integration test qua HTTP để xác nhận argument resolver, binder customizer, Pageable và controller cùng hoạt động như dự kiến.

## 13. Những lỗi thường gặp

- **Để mọi property mặc định được bind.** Dùng `excludeUnlistedProperties(true)` rồi allowlist bằng `including(...)`.
- **Chỉ exclude password nhưng quên tenant hoặc cờ nội bộ khác.** Allowlist giúp field mới thêm vào entity không tự động trở thành filter công khai.
- **Cho rằng binder là authorization.** Luôn kết hợp predicate với điều kiện tenant/owner/permission từ server.
- **Đưa entity trực tiếp ra response.** Dùng DTO/projection để kiểm soát field được trả về.
- **Cho rằng filter allowlist cũng giới hạn sort.** Validate `Sort` riêng.
- **Cho rằng property lạ luôn trả HTTP 400.** Nếu cần reject, validate tên query parameter ở tầng HTTP.
- **Dùng binding toàn cục cho mọi String path.** Ưu tiên binding theo từng field được công khai.
- **Cho phép nested association không giới hạn.** Kiểm soát join, cardinality và dữ liệu liên quan.
- **Không giới hạn page size hoặc số giá trị lặp.** Đặt giới hạn và theo dõi chi phí truy vấn.
- **Chỉ test repository, không test endpoint.** Kiểm thử cả web argument resolver và security scope.

## 14. Quy trình triển khai an toàn

1. Xác định endpoint cần những filter nào; viết hợp đồng query parameter rõ ràng.
2. Cấu hình Querydsl Jakarta artifact và annotation processor tương thích để sinh Q class.
3. Cho repository kế thừa `QuerydslPredicateExecutor<T>` và `QuerydslBinderCustomizer<QEntity>`.
4. Bật `excludeUnlistedProperties(true)` và chỉ `including(...)` các path được duyệt.
5. Định nghĩa phép so khớp riêng cho từng path; không nhận biểu thức Querydsl tùy ý từ client.
6. Dùng `@QuerydslPredicate(root = Entity.class)` ở controller.
7. Kết hợp predicate client với tenant/owner/authorization predicate bắt buộc ở service.
8. Trả DTO/projection; không expose entity nội bộ.
9. Validate sort, page size, độ dài chuỗi và số lượng giá trị lặp.
10. Kiểm thử qua HTTP với filter hợp lệ, property bị chặn, tenant khác và input không hợp lệ.

## Kết luận

`@QuerydslPredicate` giúp chuyển query parameter thành Querydsl predicate, còn `QuerydslBinderCustomizer` và `QuerydslBindings` xác định thuộc tính nào được công khai và cách chúng được so khớp. Hãy bật chế độ exclude unlisted, chỉ allowlist các field cần thiết, kết hợp điều kiện tenant/authorization do server tạo, trả DTO và kiểm soát Pageable/Sort riêng. Predicate từ web là dữ liệu đầu vào không đáng tin cậy; allowlist và kiểm thử HTTP giúp API có hợp đồng tìm kiếm rõ ràng, an toàn và dễ bảo trì.
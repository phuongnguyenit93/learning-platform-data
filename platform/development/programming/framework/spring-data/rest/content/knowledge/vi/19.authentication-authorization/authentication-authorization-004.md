# @PreAuthorize tại repository và phương thức CRUD

## Mục tiêu

Spring Data REST tự động công bố các repository thành REST resource. Khi ứng dụng bật Spring Security, có thể dùng `@PreAuthorize` để kiểm tra quyền ngay tại phương thức repository trước khi Spring Data REST thực hiện thao tác đọc hoặc ghi.

Có thể đặt `@PreAuthorize` ở cấp repository để áp dụng một chính sách mặc định cho toàn bộ repository, sau đó ghi đè chính sách ở từng phương thức khi một thao tác cần quyền khác. Cách làm này giúp bảo vệ cả lời gọi đi qua REST exporter lẫn lời gọi repository từ service hoặc thành phần khác trong ứng dụng.

Cần hiểu rõ ba điểm:

- Method security phải được bật bằng `@EnableMethodSecurity`.
- Annotation ở cấp phương thức ghi đè annotation ở cấp repository; hai biểu thức không tự động kết hợp.
- Nếu muốn bảo vệ toàn bộ thao tác CRUD, phải kiểm tra các overload và phương thức kế thừa mà repository cung cấp, đặc biệt là các biến thể xóa.

## 1. Method security trong luồng Spring Data REST

Giả sử ứng dụng export repository Order:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends JpaRepository<Order, UUID> {
}
~~~

Các request REST thường được chuyển đến thao tác repository tương ứng:

| HTTP request | Thao tác repository thường dùng |
|---|---|
| `GET /orders` | `findAll(...)` |
| `GET /orders/{id}` | `findById(id)` |
| `POST /orders` | `save(entity)` |
| `PUT /orders/{id}` | `save(entity)` |
| `PATCH /orders/{id}` | `save(entity)` |
| `DELETE /orders/{id}` | `deleteById(id)` hoặc thao tác delete tương ứng |

Luồng xử lý khái quát:

~~~text
HTTP request
     |
     v
Spring Security filter chain
     |
     v
Spring Data REST handler
     |
     v
Repository proxy
     |
     v
Method Security interceptor (@PreAuthorize)
     |
     +---- denied ----> AccessDeniedException
     |
     v
Repository method executes
     |
     v
HTTP response
~~~

Request-level authorization trong filter chain có thể chặn request theo URL và HTTP method. Method security kiểm tra quyền tại lời gọi phương thức repository. Hai lớp này bổ sung cho nhau: một request có thể vượt qua rule ở URL nhưng vẫn bị từ chối khi gọi repository method.

Vì method security đặt ở proxy của repository, quy tắc cũng áp dụng khi service trong ứng dụng gọi cùng repository method trực tiếp. Điều này hữu ích khi cùng một repository được dùng bởi REST API, scheduled job hoặc service khác.

## 2. Bật method security

Với Spring Security hiện đại, bật pre/post method authorization bằng `@EnableMethodSecurity`:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

`prePostEnabled` mặc định là `true`, vì vậy chỉ cần `@EnableMethodSecurity` để kích hoạt `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter`.

Nếu dự án dùng phiên bản Spring Security cũ, cấu hình có thể dùng:

~~~java
@Configuration
@EnableGlobalMethodSecurity(prePostEnabled = true)
public class LegacyMethodSecurityConfiguration {
}
~~~

Không cần bật cả hai annotation. Hãy dùng cấu hình tương ứng với phiên bản Spring Security của dự án.

Một cấu hình web hiện đại có thể khai báo filter chain riêng:

~~~java
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Đây là ví dụ minh họa cho HTTP Basic. Ứng dụng thực tế có thể dùng form login, OAuth2 Resource Server, session hoặc cơ chế xác thực khác. Rule `anyRequest().authenticated()` tạo lớp bảo vệ mặc định cho các request; method security tiếp tục áp dụng các quyền chi tiết ở repository.

Không nên chỉ bật method security rồi để các endpoint không có annotation tự do truy cập. Spring Security lưu ý rằng phương thức không có annotation method-security không tự động bị bảo vệ. Hãy có một chính sách request-level mặc định trong `HttpSecurity`.

## 3. @PreAuthorize ở cấp repository

Đặt annotation trên repository interface để yêu cầu một quyền chung cho mọi phương thức được gọi qua repository proxy:

~~~java
@RepositoryRestResource(path = "orders")
@PreAuthorize("hasRole('USER')")
public interface OrderRepository
        extends JpaRepository<Order, UUID> {
}
~~~

Với cấu hình này, principal cần có authority tương ứng với role USER trước khi gọi các phương thức repository, ví dụ `findById`, `findAll`, `save` hoặc `delete`.

`hasRole('USER')` kiểm tra authority `ROLE_USER` theo role prefix mặc định của Spring Security. Nếu muốn kiểm tra một authority chính xác, có thể dùng:

~~~java
@PreAuthorize("hasAuthority('order:read')")
Optional<Order> findById(UUID id);
~~~

Role phù hợp cho nhóm quyền rộng; authority như `order:read`, `order:create` hoặc `order:delete` có thể diễn đạt quyền nghiệp vụ chi tiết hơn.

Spring Data REST chính thức minh họa cách đặt `@PreAuthorize` ở cấp repository để bảo vệ toàn bộ repository. Đây là chính sách mặc định cho các phương thức, trừ phương thức được khai báo annotation riêng.

## 4. Ghi đè quyền ở từng phương thức CRUD

Khi một phương thức cần chính sách riêng, override method từ `CrudRepository`/`JpaRepository` và đặt `@PreAuthorize` trực tiếp lên method:

~~~java
@RepositoryRestResource(path = "orders")
@PreAuthorize("hasRole('USER')")
public interface OrderRepository
        extends JpaRepository<Order, UUID> {

    @Override
    @PreAuthorize("hasRole('ADMIN')")
    Optional<Order> findById(UUID id);

    @Override
    @PreAuthorize("hasRole('ADMIN')")
    void deleteById(UUID id);

    @Override
    @PreAuthorize("hasRole('ADMIN')")
    void delete(Order order);

    @Override
    @PreAuthorize("hasRole('ADMIN')")
    void deleteAll(Iterable<? extends Order> orders);

    @Override
    @PreAuthorize("hasRole('ADMIN')")
    void deleteAll();
}
~~~

Ý nghĩa:

- Repository-level policy yêu cầu role USER cho các method không có annotation riêng.
- `findById` và các method xóa yêu cầu role ADMIN.
- Các method có annotation riêng dùng biểu thức method-level thay cho biểu thức repository-level.

**Hai mức annotation không tự động kết hợp.** Nếu repository yêu cầu USER nhưng method có `@PreAuthorize("hasRole('ADMIN')")`, method đó chỉ kiểm tra biểu thức ADMIN. Nếu nghiệp vụ yêu cầu người gọi phải có cả hai role, hãy viết điều kiện kết hợp rõ ràng:

~~~java
@PreAuthorize("hasRole('USER') and hasRole('ADMIN')")
void deleteById(UUID id);
~~~

Không nên nghĩ rằng method-level ADMIN sẽ tự động kế thừa và cộng thêm điều kiện USER từ repository. Đây là quy tắc quan trọng khi phân quyền theo nhiều cấp.

## 5. Bảo vệ đầy đủ các phương thức xóa

Một lỗi thường gặp là chỉ override `deleteById` rồi cho rằng mọi thao tác xóa đã được bảo vệ. `CrudRepository` cung cấp nhiều biến thể xóa:

- `deleteById(ID id)`
- `delete(T entity)`
- `deleteAll(Iterable<? extends T> entities)`
- `deleteAll()`

Tài liệu Spring Data REST nhấn mạnh cần override tất cả các phương thức xóa này nếu muốn đặt chính sách riêng cho thao tác delete. Nếu chỉ bảo vệ một overload, lời gọi qua overload khác có thể vẫn dùng chính sách ở cấp repository hoặc chính sách khác mà ứng dụng không dự định.

Ví dụ tách quyền đọc và quyền xóa:

~~~java
@RepositoryRestResource(path = "orders")
@PreAuthorize("hasAuthority('order:read')")
public interface OrderRepository
        extends JpaRepository<Order, UUID> {

    @Override
    @PreAuthorize("hasAuthority('order:delete')")
    void deleteById(UUID id);

    @Override
    @PreAuthorize("hasAuthority('order:delete')")
    void delete(Order order);

    @Override
    @PreAuthorize("hasAuthority('order:delete')")
    void deleteAll(Iterable<? extends Order> orders);

    @Override
    @PreAuthorize("hasAuthority('order:delete')")
    void deleteAll();
}
~~~

Hãy đối chiếu interface CRUD thực tế của phiên bản Spring Data đang dùng. Nếu interface có thêm phương thức ghi hoặc overload khác, hãy áp dụng chính sách tương ứng cho những method đó. Đồng thời kiểm tra các custom repository method có khả năng thay đổi dữ liệu.

## 6. Bảo vệ thao tác tạo và cập nhật

Các phương thức ghi chính của repository gồm:

- `save(S entity)`
- `saveAll(Iterable<S> entities)`

Có thể đặt quyền riêng cho chúng:

~~~java
@RepositoryRestResource(path = "orders")
@PreAuthorize("hasAuthority('order:read')")
public interface OrderRepository
        extends JpaRepository<Order, UUID> {

    @Override
    @PreAuthorize("hasAuthority('order:write')")
    <S extends Order> S save(S entity);

    @Override
    @PreAuthorize("hasAuthority('order:write')")
    <S extends Order> List<S> saveAll(Iterable<S> entities);
}
~~~

Cần chú ý Spring Data REST thường dùng cùng repository save operation cho POST tạo mới và PUT/PATCH cập nhật item. Vì vậy, một `@PreAuthorize` trên `save` áp dụng cho lời gọi save bất kể request bắt đầu từ POST, PUT hay PATCH.

Nếu chính sách cần role khác nhau cho POST và PUT/PATCH, chỉ annotation trên `save` không đủ để phân biệt. Có thể dùng request-level authorization theo HTTP method/path, hoặc tạo custom controller/service với các phương thức nghiệp vụ riêng rồi đặt method security trên từng phương thức đó.

Ví dụ phân biệt ở request layer:

~~~java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.POST, "/orders").hasAuthority("order:create")
    .requestMatchers(HttpMethod.PUT, "/orders/**").hasAuthority("order:update")
    .requestMatchers(HttpMethod.PATCH, "/orders/**").hasAuthority("order:update")
    .anyRequest().authenticated()
)
~~~

Request-level rule và method-level rule đều phải được thỏa mãn. Nếu repository `save` còn yêu cầu `order:write`, principal phải có cả quyền tương ứng ở hai lớp hoặc ứng dụng cần tổ chức authority/role hierarchy phù hợp.

## 7. Bảo vệ truy vấn theo quyền của người dùng

`@PreAuthorize` không chỉ kiểm tra role. SpEL có thể dùng principal, tham số method và bean nghiệp vụ để quyết định quyền.

Ví dụ chỉ cho phép người dùng đọc Order nếu họ là chủ sở hữu hoặc có quyền quản trị:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository
        extends JpaRepository<Order, UUID> {

    @Override
    @PreAuthorize("@orderAuthorization.canRead(authentication, #id)")
    Optional<Order> findById(@Param("id") UUID id);
}
~~~

Bean kiểm tra quyền:

~~~java
@Component("orderAuthorization")
public class OrderAuthorization {

    private final OrderPermissionService permissionService;

    public OrderAuthorization(OrderPermissionService permissionService) {
        this.permissionService = permissionService;
    }

    public boolean canRead(Authentication authentication, UUID orderId) {
        return permissionService.canRead(authentication, orderId);
    }
}
~~~

`@Param("id")` cung cấp tên tham số cho biểu thức SpEL. Spring Security cũng có thể khám phá tên tham số từ `@P` hoặc khi biên dịch với tùy chọn `-parameters`. Với interface repository, khai báo tên tham số tường minh giúp biểu thức dễ đọc và ổn định.

Không nên nhúng một truy vấn phức tạp hoặc nhiều quy tắc nghiệp vụ vào chuỗi SpEL dài. Hãy chuyển logic đó vào một bean authorization chuyên trách để có thể kiểm thử riêng.

## 8. Phân biệt @PreAuthorize và @PostAuthorize

`@PreAuthorize` kiểm tra quyền trước khi method được thực thi. Đây là lựa chọn phù hợp cho các phương thức ghi vì có thể từ chối request trước khi thay đổi database.

`@PostAuthorize` kiểm tra kết quả sau khi method chạy. Ví dụ:

~~~java
@PostAuthorize("returnObject.orElse(null)?.owner == authentication.name")
Optional<Order> findById(UUID id);
~~~

Cách này có thể hữu ích khi cần kiểm tra quyền dựa trên entity vừa đọc. Tuy nhiên, không nên dùng `@PostAuthorize` để bảo vệ phương thức ghi như `save` hoặc `delete`: dữ liệu có thể đã được thay đổi trước khi điều kiện hậu kiểm từ chối kết quả.

Với thao tác ghi, hãy kiểm tra quyền trước khi thực thi bằng `@PreAuthorize`. Nếu quyền phụ thuộc owner của entity hiện có, có thể gọi bean authorization từ SpEL để tải/kiểm tra ownership trước khi cho phép thao tác.

## 9. Kết hợp method security với request-level security

Method security và URL security bảo vệ các điểm khác nhau:

| Lớp bảo vệ | Kiểm tra | Ví dụ |
|---|---|---|
| Request-level | URL, HTTP method, trạng thái xác thực | Chỉ ADMIN được gọi DELETE /orders/** |
| Repository-level | Mọi lời gọi repository method | Người dùng cần order:read để gọi repository |
| Method-level | Một thao tác CRUD cụ thể | Chỉ order:delete được gọi deleteById |
| Object-level | Quyền trên entity cụ thể | Chỉ owner hoặc ADMIN được đọc Order 42 |

Ví dụ request-level rule:

~~~java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.DELETE, "/orders/**")
        .hasAuthority("order:delete")
    .requestMatchers("/orders/**")
        .authenticated()
    .anyRequest().authenticated()
)
~~~

Nếu chỉ dùng request-level security, code nội bộ gọi repository trực tiếp có thể không đi qua HTTP filter chain. Method security ở repository bảo vệ cả các lời gọi đó.

Nếu chỉ dùng method security, những endpoint khác không gọi repository hoặc method chưa được annotate vẫn cần chính sách request-level. Hãy dùng cả hai lớp theo ranh giới trách nhiệm của ứng dụng.

## 10. Kiểm thử quyền truy cập bằng MockMvc

Nên kiểm tra cả người dùng được phép và bị từ chối. Spring Security Test hỗ trợ `@WithMockUser` để tạo Authentication trong test.

Ví dụ:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderRepositorySecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(roles = "USER")
    void userCanReadOrders() throws Exception {
        mvc.perform(get("/orders")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(roles = "USER")
    void userCannotDeleteOrder() throws Exception {
        mvc.perform(delete("/orders/00000000-0000-0000-0000-000000000001"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanDeleteOrder() throws Exception {
        mvc.perform(delete("/orders/00000000-0000-0000-0000-000000000001"))
            .andExpect(status().isNoContent());
    }

    @Test
    void anonymousUserCannotReadOrders() throws Exception {
        mvc.perform(get("/orders")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Đây là khung test tích hợp; cần tạo fixture có ID phù hợp và điều chỉnh status thành công theo cấu hình Spring Data REST của ứng dụng. Nếu dùng HTTP Basic, form login hoặc bearer token, cấu hình request test tương ứng. Với `@WithMockUser(roles = "USER")`, Spring Security tạo authority `ROLE_USER`.

Ngoài MockMvc, nên kiểm thử trực tiếp repository proxy với `@WithMockUser` hoặc `SecurityContext` phù hợp để xác nhận method security vẫn hoạt động khi service gọi repository không thông qua REST.

Các tình huống cần có:

- Anonymous bị chặn ở request layer.
- USER đọc được tài nguyên theo policy.
- USER không thể gọi method delete được dành cho ADMIN.
- ADMIN có thể gọi các method xóa được cho phép.
- Các overload delete khác cũng bị chặn đúng.
- Method-level annotation ghi đè policy repository như dự kiến.
- Custom finder và custom write method cũng có policy rõ ràng.
- Kiểm tra dữ liệu không thay đổi sau request bị từ chối.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Cách xử lý |
|---|---|---|
| @PreAuthorize không có tác dụng | Chưa bật method security | Thêm @EnableMethodSecurity hoặc cấu hình legacy phù hợp |
| REST request bị chặn dù URL rule cho phép | Repository method có policy riêng không thỏa | Kiểm tra annotation cấp repository và method |
| Method-level ADMIN vẫn không yêu cầu USER | Method-level annotation ghi đè repository-level | Kết hợp cả hai điều kiện trong cùng SpEL nếu cần |
| Chỉ deleteById bị bảo vệ | Các overload delete khác chưa được override | Bảo vệ đủ các phương thức xóa của CrudRepository |
| POST và PUT không có quyền riêng | Cả hai cùng đi qua save | Phân biệt bằng request matcher hoặc custom service method |
| Repository method được gọi từ service mà không bị chặn | Method security chưa bật hoặc lời gọi không đi qua proxy | Kiểm tra proxy và cấu hình method security |
| User có role nhưng vẫn nhận 403 | Role/authority name không khớp prefix | Kiểm tra ROLE_ và dùng hasRole/hasAuthority nhất quán |
| SpEL không tìm thấy tham số | Tên tham số không được khám phá | Dùng @Param, @P hoặc biên dịch với -parameters |
| Dữ liệu đã ghi rồi mới bị từ chối | Dùng @PostAuthorize trên phương thức ghi | Dùng @PreAuthorize trước khi thực thi |
| Endpoint khác vẫn truy cập được | Method chưa annotate và request layer quá rộng | Thêm catch-all authorization rule trong HttpSecurity |

## 12. Checklist triển khai @PreAuthorize

- Bật method security bằng `@EnableMethodSecurity`.
- Đặt chính sách mặc định ở repository interface khi mọi thao tác cần cùng một quyền.
- Override method và đặt annotation riêng khi một CRUD operation cần quyền khác.
- Nhớ rằng method-level annotation ghi đè repository-level annotation, không tự kết hợp.
- Bảo vệ đủ các overload delete: deleteById, delete, deleteAll(Iterable), deleteAll().
- Xác định các phương thức save/saveAll và custom method có thể ghi dữ liệu.
- Nếu POST và PUT/PATCH cần quyền khác nhau, dùng request-level method/path hoặc custom service/controller.
- Dùng bean authorization cho kiểm tra ownership hoặc quyền theo từng entity.
- Ưu tiên @PreAuthorize trước thao tác ghi; thận trọng với @PostAuthorize.
- Kết hợp request-level và method-level security; có catch-all rule cho request.
- Kiểm thử cả role được phép, role bị từ chối, anonymous và mọi overload quan trọng.
- Kiểm tra dữ liệu database sau request bị từ chối.

## Kết luận

`@PreAuthorize` có thể đặt ở cấp repository để bảo vệ toàn bộ lời gọi repository, hoặc ở từng phương thức CRUD để áp dụng chính sách cụ thể. Spring Data REST gọi repository proxy khi xử lý request, vì vậy method security kiểm tra quyền ngay tại thao tác dữ liệu và cũng bảo vệ lời gọi từ service trong ứng dụng. Method-level annotation ghi đè repository-level annotation; nếu cần cả hai điều kiện, phải viết chúng trong cùng biểu thức. Hãy bật `@EnableMethodSecurity`, override đầy đủ các overload xóa, phân biệt rõ quyền POST với PUT/PATCH khi chúng cùng dùng `save`, và kiểm thử cả request-level lẫn repository-level authorization.

## Tài liệu tham khảo

- Spring Data REST – Security and repository method authorization: https://docs.spring.io/spring-data/rest/reference/security.html
- Spring Security – Method Security, @PreAuthorize and @PostAuthorize: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Data Commons – CrudRepository API and CRUD methods: https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html
- Spring Security Test – Method security testing: https://docs.spring.io/spring-security/reference/servlet/test/method.html

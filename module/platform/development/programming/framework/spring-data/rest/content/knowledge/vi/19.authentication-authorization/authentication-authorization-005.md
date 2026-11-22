# Quy tắc phương thức ghi đè quy tắc bảo mật ở cấp repository

Spring Data REST xuất các repository thành REST API. Có thể bảo vệ các thao tác repository bằng Spring Security method security. Một quy tắc đặt ở cấp repository interface đóng vai trò mặc định cho các method; khi một method khai báo quy tắc riêng, quy tắc ở cấp method được ưu tiên cho chính method đó.

Cơ chế này giúp áp dụng chính sách chung cho repository, đồng thời giới hạn hoặc mở rộng quyền cho một số thao tác cụ thể như đọc, tìm kiếm, lưu hoặc xóa. Cần hiểu rõ rằng quy tắc ở cấp method **thay thế** quy tắc cùng loại ở cấp repository cho method đó; chúng không tự động được kết hợp bằng phép AND.

## 1. Bật method security

Spring Security method security cần được bật rõ ràng trong cấu hình ứng dụng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {
}
~~~

Với Spring Boot, thêm dependency Spring Security phù hợp, ví dụ:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
~~~

**`@EnableMethodSecurity`** đăng ký các interceptor để xử lý annotation như:

- **`@PreAuthorize`**: kiểm tra quyền trước khi gọi method.
- **`@PostAuthorize`**: kiểm tra kết quả sau khi method thực thi.
- **`@PreFilter`** và **`@PostFilter`**: lọc phần tử của collection hoặc tham số theo biểu thức bảo mật.
- **`@Secured`** và **`@RolesAllowed`**: các dạng khai báo quyền khác khi được bật tương ứng.

Trong Spring Security hiện đại, **`@EnableMethodSecurity`** thay thế cấu hình cũ **`@EnableGlobalMethodSecurity`**. Không cần bật cả hai.

## 2. Đặt quy tắc mặc định ở cấp repository

Có thể đặt **`@PreAuthorize`** trực tiếp trên repository interface. Quy tắc đó áp dụng mặc định cho các method của repository khi không có quy tắc method-level tương ứng.

Ví dụ, yêu cầu người dùng có role USER mới được truy cập các thao tác repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.security.access.prepost.PreAuthorize;

@RepositoryRestResource(path = "orders")
@PreAuthorize("hasRole('USER')")
public interface OrderRepository extends JpaRepository<Order, Long> {
}
~~~

Trong ví dụ:

- **`@RepositoryRestResource`** cấu hình cách repository được xuất thành REST resource.
- **`@PreAuthorize("hasRole('USER')")`** đặt chính sách mặc định cho các method.
- Người dùng không có quyền phù hợp bị chặn khi gọi method qua Spring-managed repository proxy.

**`hasRole('USER')`** là cách viết ngắn cho authority **`ROLE_USER`**. Nếu muốn so khớp chính xác authority, dùng:

~~~java
@PreAuthorize("hasAuthority('ROLE_USER')")
~~~

Không nhầm annotation **`@RepositoryRestResource`** với cấu hình bảo mật. Annotation đó điều khiển việc xuất resource và mapping REST; **`@PreAuthorize`** mới là quy tắc authorization.

## 3. Ghi đè quy tắc bằng annotation ở cấp method

Khi một method cần chính sách khác với mặc định của repository, đặt **`@PreAuthorize`** trực tiếp trên method.

Ví dụ: mọi thao tác mặc định cần role USER, nhưng xóa order chỉ dành cho ADMIN:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.security.access.prepost.PreAuthorize;

@RepositoryRestResource(path = "orders")
@PreAuthorize("hasRole('USER')")
public interface OrderRepository extends JpaRepository<Order, Long> {

    @Override
    @PreAuthorize("hasRole('ADMIN')")
    void deleteById(Long id);
}
~~~

Quy tắc của method **`deleteById`** là **`hasRole('ADMIN')`**. Spring Security dùng biểu thức method-level cho thao tác này thay cho biểu thức cấp repository **`hasRole('USER')`**.

Các method khác không có annotation riêng vẫn chịu quy tắc mặc định ở cấp repository.

| Method | Quy tắc áp dụng |
|---|---|
| **`findAll()`** | **`hasRole('USER')`** từ repository |
| **`findById(id)`** | **`hasRole('USER')`** từ repository |
| **`save(entity)`** | **`hasRole('USER')`** từ repository |
| **`deleteById(id)`** | **`hasRole('ADMIN')`** từ method |

Điểm cần nhớ: nếu ADMIN không có role USER, ADMIN vẫn có thể gọi **`deleteById`** theo biểu thức method-level trong ví dụ. Quy tắc USER ở cấp repository không được tự động cộng thêm vào quy tắc ADMIN của method.

## 4. Quy tắc method-level thay thế, không tự động kết hợp

Giả sử repository có:

~~~java
@PreAuthorize("hasRole('USER')")
public interface OrderRepository extends JpaRepository<Order, Long> {

    @PreAuthorize("hasRole('ADMIN')")
    void deleteById(Long id);
}
~~~

Với method **`deleteById`**, biểu thức được đánh giá là **`hasRole('ADMIN')`**. Nó không được hiểu thành:

~~~text
hasRole('USER') AND hasRole('ADMIN')
~~~

Nếu nghiệp vụ yêu cầu người gọi phải có đồng thời cả hai role, hãy viết rõ điều kiện kết hợp:

~~~java
@PreAuthorize("hasRole('USER') and hasRole('ADMIN')")
void deleteById(Long id);
~~~

Nếu muốn cho phép một trong hai role:

~~~java
@PreAuthorize("hasAnyRole('USER', 'ADMIN')")
void deleteById(Long id);
~~~

Do method-level có thể thay thế chính sách chung, cần kiểm tra cẩn thận mỗi method được gắn annotation riêng. Một biểu thức quá rộng có thể vô tình mở quyền cho người dùng mà quy tắc cấp repository trước đó không cho phép.

## 5. Ghi đè method CRUD được kế thừa

Các repository thường kế thừa method từ **`CrudRepository`**, **`ListCrudRepository`** hoặc **`JpaRepository`**. Nếu muốn áp dụng quy tắc riêng cho một method kế thừa, hãy khai báo lại method đó trong interface repository cụ thể và gắn annotation trên khai báo override.

Ví dụ giới hạn thao tác xóa và lưu:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize("hasRole('USER')")
public interface OrderRepository extends JpaRepository<Order, Long> {

    @Override
    @PreAuthorize("hasRole('ADMIN')")
    void deleteById(Long id);

    @Override
    @PreAuthorize("hasRole('EDITOR') or hasRole('ADMIN')")
    <S extends Order> S save(S entity);
}
~~~

Khi override:

- Giữ đúng tên method và tham số của interface cha.
- Giữ kiểu trả về tương thích với hợp đồng kế thừa.
- Đặt annotation trên method declaration được repository proxy sử dụng.
- Chỉ override những method thực sự cần chính sách riêng.

Nếu không khai báo lại method kế thừa, method đó tiếp tục chịu chính sách mặc định ở cấp repository.

## 6. Áp dụng quy tắc riêng cho query method

Quy tắc method-level cũng có thể bảo vệ các query method được Spring Data REST xuất dưới **`/search`**.

Ví dụ repository có chính sách chung cho USER, nhưng một truy vấn quản trị chỉ dành cho ADMIN:

~~~java
import java.util.List;

import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RestResource;
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize("hasRole('USER')")
public interface OrderRepository extends JpaRepository<Order, Long> {

    List<Order> findByStatus(String status);

    @RestResource(path = "all-customers")
    @PreAuthorize("hasRole('ADMIN')")
    List<Order> findAllByCustomerId(@Param("customerId") Long customerId);
}
~~~

Method **`findByStatus`** dùng quy tắc USER mặc định. Method **`findAllByCustomerId`** dùng quy tắc ADMIN riêng.

Khi client gọi query resource, Spring Data REST gọi repository method thông qua proxy. Method security sẽ kiểm tra quyền tại thời điểm gọi. Nếu truy vấn bị chặn, client không nhận được kết quả chỉ vì endpoint search đã được xuất.

## 7. Dùng biểu thức bảo mật theo tham số và dữ liệu

**`@PreAuthorize`** hỗ trợ SpEL, vì vậy có thể kiểm tra tham số đầu vào thay vì chỉ kiểm tra role.

Ví dụ chỉ cho phép người dùng tìm order trong phạm vi account của chính họ hoặc người có role ADMIN:

~~~java
@PreAuthorize(
    "hasRole('ADMIN') or #accountId == authentication.principal.accountId"
)
List<Order> findByAccountId(@Param("accountId") Long accountId);
~~~

Tên tham số dùng trong SpEL phải được Spring nhận diện. Có thể dùng **`@P`** hoặc **`@Param`** theo cấu hình và phiên bản phù hợp, đồng thời bật biên dịch lưu tên tham số nếu biểu thức dựa trên tên Java.

Đối với kiểm tra dữ liệu trả về, **`@PostAuthorize`** có thể kiểm tra object sau khi method hoàn tất:

~~~java
@PostAuthorize(
    "returnObject.isEmpty() or " +
    "returnObject.get().owner == authentication.name"
)
Optional<Order> findById(Long id);
~~~

Cần dùng biểu thức phù hợp với kiểu trả về thực tế. Với collection lớn, tránh tải toàn bộ dữ liệu rồi mới lọc bằng **`@PostFilter`**; hãy ưu tiên đưa điều kiện quyền vào truy vấn hoặc service để giới hạn dữ liệu ngay tại database.

## 8. Phân biệt method security và HTTP request security

Method security và HTTP request security hoạt động ở hai lớp khác nhau:

1. HTTP security filter chain kiểm tra request dựa trên URL, HTTP method, authentication và request matcher.
2. Nếu request vượt qua filter chain và gọi tới repository proxy, method security tiếp tục kiểm tra annotation trên repository/method.

Ví dụ cấu hình HTTP:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/orders/**").authenticated()
            .anyRequest().permitAll()
        )
        .build();
}
~~~

Nếu filter chain từ chối request, quy tắc **`@PreAuthorize`** ở method không thể cho phép request đi tiếp. Ngược lại, request vượt qua URL matcher vẫn có thể bị method security từ chối.

Do đó, method-level override chỉ thay thế quy tắc method-level ở repository/interface. Nó không ghi đè một quy tắc URL độc lập trong **`HttpSecurity`**, cũng không vô hiệu hóa các kiểm tra CSRF, authentication hoặc các filter khác.

## 9. Phân biệt role, authority và trạng thái truy cập

Spring Security cung cấp một số biểu thức thường dùng:

| Biểu thức | Ý nghĩa |
|---|---|
| **`hasRole('ADMIN')`** | Kiểm tra authority mặc định có prefix **`ROLE_`** |
| **`hasAuthority('order:read')`** | Kiểm tra authority chính xác |
| **`hasAnyRole('USER', 'ADMIN')`** | Cho phép một trong các role |
| **`hasAnyAuthority('order:read', 'order:write')`** | Cho phép một trong các authority |
| **`isAuthenticated()`** | Yêu cầu người dùng đã xác thực |
| **`permitAll()`** | Cho phép mọi người gọi qua method security |
| **`denyAll()`** | Từ chối mọi lời gọi qua method security |

Ví dụ dùng permission theo chức năng:

~~~java
@PreAuthorize("hasAuthority('order:read')")
List<Order> findByStatus(String status);

@PreAuthorize("hasAuthority('order:delete')")
void deleteById(Long id);
~~~

Dùng authority chi tiết có thể dễ quản lý hơn khi quyền không hoàn toàn tương ứng với vai trò người dùng.

## 10. Kiểm tra method-level override

Nên kiểm tra bằng integration test có authentication khác nhau và gọi endpoint thực tế.

Ví dụ với Spring Security Test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderSecurityTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithMockUser(roles = "USER")
    void userCanReadOrders() throws Exception {
        mockMvc.perform(get("/orders"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(roles = "USER")
    void userCannotDeleteOrder() throws Exception {
        mockMvc.perform(delete("/orders/1"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanDeleteOrder() throws Exception {
        mockMvc.perform(delete("/orders/1"))
                .andExpect(status().is2xxSuccessful());
    }
}
~~~

Bộ test trên giả định HTTP filter chain cho phép các request đã đăng nhập đi tới repository và dữ liệu order số 1 tồn tại. Điều chỉnh response mong đợi theo contract của ứng dụng.

Có thể kiểm tra thêm query method bằng cách gọi **`/orders/search/...`** với USER và ADMIN để xác nhận quy tắc method-level được thực thi cả qua search resource.

Các trạng thái thường gặp:

- **`401 Unauthorized`**: request chưa được xác thực hoặc cần cơ chế authentication.
- **`403 Forbidden`**: người dùng đã xác thực nhưng không đủ quyền.
- Một số cấu hình có thể tùy chỉnh cách chuyển exception bảo mật thành response; hãy kiểm tra status và body thực tế của API.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Annotation không có tác dụng | Chưa bật **`@EnableMethodSecurity`** | Bật method security và kiểm tra cấu hình |
| Method kế thừa không dùng rule riêng | Chưa override method trong repository interface | Khai báo lại method và gắn annotation |
| Method ADMIN vẫn bị chặn | HTTP filter chain hoặc rule khác từ chối request trước đó | Kiểm tra request matcher và các filter |
| Method-level cho phép USER dù repository yêu cầu ADMIN | Method annotation thay thế quy tắc cấp repository | Kiểm tra biểu thức và viết rõ điều kiện kết hợp nếu cần |
| Người dùng không có role vẫn gọi được | Method không đi qua Spring proxy hoặc annotation không được phát hiện | Kiểm tra bean, proxy và đường gọi |
| Tự gọi method trong cùng bean không bị chặn | Self-invocation bỏ qua proxy AOP | Gọi qua Spring-managed bean/proxy hoặc thiết kế lại ranh giới service |
| Query method bị lộ dữ liệu | Endpoint được xuất nhưng chưa có method security phù hợp | Gắn quy tắc trên query method và kiểm tra cả URL-level security |

## 12. Quy trình thiết kế chính sách

Khi bảo vệ một repository, thực hiện theo thứ tự:

1. Chọn chính sách mặc định cho repository, ví dụ mọi thao tác yêu cầu USER.
2. Liệt kê các method cần quyền khác như xóa, quản trị hoặc truy vấn dữ liệu nhạy cảm.
3. Override method CRUD kế thừa nếu cần và đặt **`@PreAuthorize`** trực tiếp trên method.
4. Viết biểu thức method-level hoàn chỉnh vì nó thay thế biểu thức cùng loại ở cấp repository.
5. Kiểm tra các URL matcher trong HTTP filter chain để bảo đảm request có thể đi tới method cần gọi.
6. Test từng vai trò cho cả collection resource, item resource, query method và thao tác ghi.
7. Dùng authority theo chức năng hoặc kiểm tra quyền theo chủ sở hữu khi nghiệp vụ cần kiểm soát chi tiết.

Chính sách cấp repository giúp đặt mặc định nhất quán. Quy tắc method-level cho phép điều chỉnh từng thao tác với quyền cụ thể. Hiểu rõ thứ tự ưu tiên và ranh giới giữa HTTP security với method security giúp tránh vô tình mở quyền hoặc khóa nhầm endpoint.

Tài liệu tham khảo chính thức:

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Expression-Based Access Control](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Data REST — Security](https://docs.spring.io/spring-data/rest/reference/security.html)

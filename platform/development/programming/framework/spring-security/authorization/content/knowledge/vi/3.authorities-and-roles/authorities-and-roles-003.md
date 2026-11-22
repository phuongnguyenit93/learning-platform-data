# hasAuthority và hasRole: quy tắc tiền tố ROLE_

> **Spring Security – authorization** · **Nhóm:** Authority và role  
> Trọng tâm: ý nghĩa của `GrantedAuthority`, phép so khớp chính xác của `hasAuthority`, cách `hasRole` xử lý tiền tố `ROLE_`, và những khác biệt cần chú ý giữa HTTP authorization, method security và dữ liệu người dùng.

## 1. Tình huống mở đầu: cùng chữ ADMIN nhưng kết quả khác nhau

Giả sử một người dùng đã đăng nhập có danh sách authority như sau:

~~~text
username = "an"
authorities = ["ROLE_ADMIN", "invoice:read"]
~~~

Trong cấu hình Spring Security thông dụng, ba điều kiện sau **không giống nhau**:

~~~java
.hasRole("ADMIN")                 // Kiểm tra authority ROLE_ADMIN
.hasAuthority("ROLE_ADMIN")       // Kiểm tra đúng chuỗi ROLE_ADMIN
.hasAuthority("ADMIN")            // Kiểm tra đúng chuỗi ADMIN
~~~

Hai điều kiện đầu cho phép người dùng An đi qua; điều kiện cuối từ chối vì danh sách authority **không có chuỗi `ADMIN`**.

Nhầm lẫn thường xuất phát từ việc coi “role trong nghiệp vụ”, “chuỗi authority lưu trong `Authentication`” và “tham số truyền vào hàm kiểm tra” là một thứ. Cần nắm rõ ba tầng:

1. **Role nghiệp vụ**: tên nhóm quyền, ví dụ `ADMIN`, `EDITOR`.
2. **GrantedAuthority**: dữ liệu thực sự được gắn vào một `Authentication`, ví dụ `ROLE_ADMIN`.
3. **Authorization rule**: cách Spring Security quyết định xem authority hiện có có thỏa điều kiện hay không.

Tiền tố `ROLE_` là một **quy ước trong kiểm tra role**; nó không tự thay đổi các chuỗi quyền đã được cấp, không tự tạo role và không tự ánh xạ permission nghiệp vụ.

## 2. `Authentication` và `GrantedAuthority`: thứ được đem đi so khớp

Sau khi xác thực, Spring Security biểu diễn chủ thể bằng đối tượng `Authentication`. Ngoài principal, credentials và trạng thái xác thực, đối tượng này chứa collection các `GrantedAuthority`. Một authority dạng chuỗi thông dụng được biểu diễn qua `SimpleGrantedAuthority`.

Ví dụ một tập authority:

~~~text
Authentication
  principal: an
  authenticated: true
  authorities:
    - ROLE_ADMIN
    - invoice:read
    - SCOPE_invoices.read
~~~

Điểm quan trọng:

- `ROLE_ADMIN` có thể được ứng dụng dùng làm **authority biểu diễn role ADMIN**.
- `invoice:read` có thể được ứng dụng dùng làm **permission đọc hóa đơn**.
- `SCOPE_invoices.read` có thể đến từ **OAuth 2.0 scope** đã được ánh xạ từ access token.
- Dù khác ý nghĩa nghiệp vụ, cả ba đều có thể được chứa trong cùng một collection `GrantedAuthority`.
- `getAuthority()` của một `GrantedAuthority` dạng chuỗi thường trả về chuỗi để so khớp. Một số implementation phức tạp có thể không biểu diễn bằng một chuỗi; khi đó cần bộ kiểm tra chuyên biệt.

Ví dụ Java trong một ứng dụng đã có dependency Spring Security:

~~~java
import java.util.List;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

Authentication authentication =
        new UsernamePasswordAuthenticationToken(
                "an",
                null,
                List.of(
                        new SimpleGrantedAuthority("ROLE_ADMIN"),
                        new SimpleGrantedAuthority("invoice:read"),
                        new SimpleGrantedAuthority("SCOPE_invoices.read")
                )
        );

// authentication.getAuthorities() chứa ba authority đã truyền vào.
~~~

Đây là **đoạn minh họa trong ứng dụng Spring**, không phải chương trình độc lập. Constructor có collection authorities tạo một authentication token được đánh dấu đã xác thực; trong ứng dụng thật chỉ code thuộc lớp bảo mật đáng tin cậy mới được dựng authentication như vậy. Không nhận role hoặc authorities tự khai từ HTTP request rồi đánh dấu token đã xác thực.

**Vì sao phải xem authorities thực tế?** Khi rule bị từ chối, lỗi có thể nằm ở nguồn cấp quyền hoặc converter, không phải ở bộ so khớp. Một chuỗi `ADMIN` từ cơ sở dữ liệu không tự biến thành `ROLE_ADMIN` trong `Authentication` nếu ứng dụng chưa ánh xạ.

## 3. `hasAuthority`: so khớp chuỗi đúng nguyên văn

`hasAuthority("X")` hỏi liệu tập granted authorities có authority **đúng bằng `X`** hay không, theo cơ chế kiểm tra chuỗi thông dụng. Nó không tự thêm `ROLE_`, không tự chuẩn hóa chữ hoa/chữ thường, không tự diễn giải dấu chấm/hai chấm hay suy luận cấp bậc quyền.

Ví dụ với authorities:

~~~text
["ROLE_ADMIN", "invoice:read", "SCOPE_invoices.read"]
~~~

| Rule | Authority cần có | Kết quả |
|---|---|---|
| `hasAuthority("ROLE_ADMIN")` | `ROLE_ADMIN` | **true** |
| `hasAuthority("ADMIN")` | `ADMIN` | **false** |
| `hasAuthority("invoice:read")` | `invoice:read` | **true** |
| `hasAuthority("INVOICE:READ")` | `INVOICE:READ` | **false** |
| `hasAuthority("SCOPE_invoices.read")` | `SCOPE_invoices.read` | **true** |
| `hasAuthority("invoices.read")` | `invoices.read` | **false** |
| `hasAuthority("ROLE_USER")` | `ROLE_USER` | **false** |

Phân biệt `ADMIN` với `ROLE_ADMIN`, `invoice:read` với `Invoice:Read` và `SCOPE_invoices.read` với `invoices.read`. Nên xây dựng quy ước đặt tên tập trung, nhất quán giữa nơi cấp authority và nơi kiểm tra.

`hasAnyAuthority("A", "B")` thường yêu cầu **ít nhất một** authority khớp. Đừng diễn giải “any” thành “phải có tất cả”. Khi dùng nhiều điều kiện đồng thời, hãy viết rõ kết hợp chính sách (ví dụ expression `hasAuthority('invoice:read') and hasAuthority('SCOPE_invoices.read')`).

## 4. `hasRole`: phép kiểm tra role kèm quy ước tiền tố

Với quy ước mặc định `ROLE_`, `hasRole("ADMIN")` kiểm tra xem `Authentication` có authority `ROLE_ADMIN` không.

~~~text
hasRole("ADMIN")
    |
    v
Áp dụng tiền tố role mặc định "ROLE_"
    |
    v
Yêu cầu GrantedAuthority "ROLE_ADMIN"
~~~

Theo quy ước này:

| Rule | Authority được yêu cầu | Diễn giải |
|---|---|---|
| `hasRole("ADMIN")` | `ROLE_ADMIN` | Role ADMIN |
| `hasRole("USER")` | `ROLE_USER` | Role USER |
| `hasRole("ACCOUNTANT")` | `ROLE_ACCOUNTANT` | Role ACCOUNTANT |
| `hasAuthority("ROLE_ADMIN")` | `ROLE_ADMIN` | So khớp tường minh chuỗi role |
| `hasAuthority("ADMIN")` | `ADMIN` | So khớp authority không tiền tố |
| `hasAuthority("invoice:read")` | `invoice:read` | Kiểm tra permission nghiệp vụ nếu đã được cấp |

**Phép tương đương quan trọng trong cấu hình mặc định:**

~~~text
hasRole("ADMIN")
         ≈
hasAuthority("ROLE_ADMIN")
~~~

Ký hiệu `≈` nói về **điều kiện authority cần có** trong tình huống thông thường; không khẳng định hai API là cùng implementation hay vẫn tương đương khi tùy chỉnh tiền tố, role hierarchy hoặc authorization manager.

`hasAnyRole("ADMIN", "SUPPORT")` yêu cầu người gọi có ít nhất một trong `ROLE_ADMIN` hoặc `ROLE_SUPPORT` (trong quy ước mặc định). Việc có `ROLE_ADMIN` không mặc nhiên cấp `ROLE_USER`; quyền kế thừa chỉ có nếu cấu hình role hierarchy hoặc quy tắc cấp authority thực sự tạo ra kết quả đó.

### Một ngoại lệ dễ nhầm khi truyền chuỗi đã có `ROLE_`

**Cách viết nên dùng ở mọi nơi là `hasRole("ADMIN")`, không viết `hasRole("ROLE_ADMIN")`.** Tuy nhiên hành vi khi truyền `ROLE_ADMIN` phụ thuộc **API cụ thể**:

- Với API Java `AuthorityAuthorizationManager.hasRole("ROLE_ADMIN")` của Spring Security 6.x, JavaDoc yêu cầu tham số **không có tiền tố `ROLE_`**; implementation có thể ném `IllegalArgumentException` do tham số đã bắt đầu bằng `ROLE_`.
- Với `SecurityExpressionRoot.hasRole('ROLE_ADMIN')` trong một số cơ chế biểu thức Spring Security, expression handler nhận biết chuỗi đã có tiền tố và có thể so khớp `ROLE_ADMIN`, không nhân đôi tiền tố. Đây là điểm khác với API Java nêu trên.
- Không dùng sự khác biệt này làm quy ước code. Để dễ đọc và chuyển đổi giữa API, luôn truyền tên **role logic**, ví dụ `"ADMIN"`, vào `hasRole`, và truyền chuỗi authority **đầy đủ** vào `hasAuthority`.

Điều quan trọng là tránh tuyên bố “mọi `hasRole("ROLE_ADMIN")` đều bị nhân đôi tiền tố” hoặc “mọi nơi đều chấp nhận” – cả hai đều không chính xác cho tất cả API/phiên bản.

## 5. Ma trận kiểm tra: nhìn vào tập authority trước khi đoán kết quả

Giả sử hệ thống **không cấu hình role hierarchy** và dùng tiền tố mặc định.

| Authorities hiện tại | `hasRole("ADMIN")` | `hasAuthority("ADMIN")` | `hasAuthority("ROLE_ADMIN")` |
|---|---|---|---|
| `[]` | false | false | false |
| `["ADMIN"]` | false | true | false |
| `["ROLE_ADMIN"]` | true | false | true |
| `["ROLE_USER"]` | false | false | false |
| `["ADMIN", "ROLE_USER"]` | false | true | false |
| `["ROLE_ADMIN", "ADMIN"]` | true | true | true |
| `["SCOPE_admin"]` | false | false | false |

Các điều kiện này kiểm tra **dữ liệu authority đã được cấp**, không đọc trực tiếp cột `role` trong cơ sở dữ liệu trong mỗi lần đánh giá.

Câu hỏi quan trọng khi gặp `403 Forbidden` là: “Authority nào **được yêu cầu**, authority nào **đã hiện diện**?”. Sau đó mới kiểm tra tại sao dữ liệu đầu vào và cấu hình không khớp.

## 6. Nguồn authority: `roles(...)` và `authorities(...)` có khác nhau

Một điểm gây nhầm lẫn khác nằm ở **cách tạo user**.

### 6.1. `UserDetails` trong Spring Security

Đoạn minh họa sau nằm trong một method Java có dependency Spring Security và import phù hợp:

~~~java
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;

UserDetails fromRoles = User.withUsername("an")
        .password("{noop}demo-only")
        .roles("ADMIN")
        .build();

UserDetails fromAuthorities = User.withUsername("binh")
        .password("{noop}demo-only")
        .authorities("ROLE_ADMIN")
        .build();
~~~

Với cách tạo thông thường:

- `.roles("ADMIN")` tạo granted authority `ROLE_ADMIN`; builder xử lý tiền tố role.
- `.authorities("ROLE_ADMIN")` cấp **đúng authority được chỉ định**.
- `.authorities("ADMIN")` sẽ cấp `ADMIN` và **không** tự thêm `ROLE_`.
- Không truyền `"ROLE_ADMIN"` vào `.roles(...)` khi builder yêu cầu tên role không kèm tiền tố.
- String `{noop}demo-only` chỉ để minh họa trong tài liệu/test; không dùng mật khẩu dạng clear-text/NoOp encoder trong production.

Nếu user được tải từ database, code ánh xạ role nghiệp vụ sang `SimpleGrantedAuthority("ROLE_" + roleName)` cần đồng bộ với các rule. Cần validate tên role, tránh tự ý ghép chuỗi từ input không đáng tin và không nhân đôi tiền tố nếu dữ liệu lưu trữ vốn đã có `ROLE_`.

### 6.2. Test helper `@WithMockUser`

Spring Security Test có các cách dựng authority khác nhau:

~~~java
@WithMockUser(roles = "ADMIN")
// Tạo authority ROLE_ADMIN cho mock user.

@WithMockUser(authorities = "ROLE_ADMIN")
// Tạo chính xác authority ROLE_ADMIN.

@WithMockUser(authorities = "ADMIN")
// Tạo chính xác authority ADMIN; không thỏa hasRole("ADMIN") mặc định.
~~~

Các đoạn trên là **annotation minh họa**, cần đặt lên test method hoặc test class. Thuộc tính `roles` và `authorities` không nên chỉ định đồng thời trong cùng một `@WithMockUser`. Tạo mock user bằng `roles` không chứng minh ứng dụng đã ánh xạ JWT/database/IdP đúng; cần có test riêng cho luồng authentication thực tế.

## 7. Sử dụng trong HTTP authorization (Servlet)

Với Spring Boot 3.x / Spring Security 6.x trên servlet stack, cấu hình HTTP có thể dùng `SecurityFilterChain` và `authorizeHttpRequests`.

Ví dụ sau là **một lớp cấu hình trong ứng dụng Spring**, không phải chương trình Java độc lập. Giả định cơ chế đăng nhập và authorities được cấp chính xác bởi hệ thống:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin/**")
                    .hasRole("ADMIN")
                .requestMatchers(
                        HttpMethod.GET, "/api/invoices/**")
                    .hasAuthority("invoice:read")
                .requestMatchers("/api/support/**")
                    .hasAnyRole("ADMIN", "SUPPORT")
                .anyRequest().denyAll()
        );

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Diễn giải:

1. `/api/admin/**` yêu cầu `ROLE_ADMIN` nếu dùng tiền tố mặc định.
2. `GET /api/invoices/**` yêu cầu **đúng** `invoice:read`; chỉ có `ROLE_ADMIN` **không tự đủ** nếu permission này chưa được cấp qua mapping/hierarchy.
3. `/api/support/**` cho phép nếu có ít nhất một authority trong `ROLE_ADMIN`, `ROLE_SUPPORT`.
4. Các đường dẫn còn lại bị `denyAll()`. Hãy bổ sung rule công khai, health endpoint và các endpoint thực tế khác một cách chủ động khi xây dựng hệ thống hoàn chỉnh.
5. Quy tắc matcher được xét theo thứ tự khai báo; cần đặt đường dẫn đặc thù trước đường dẫn rộng hơn.

`httpBasic` ở đây chỉ minh họa một cơ chế xác thực; trong môi trường production phải có cấu hình người dùng/mật khẩu phù hợp và HTTPS. Ví dụ không quyết định thiết kế CSRF của ứng dụng. Nếu ứng dụng dựa trên session/cookie và có thao tác thay đổi dữ liệu, hãy bảo vệ CSRF theo mô hình sử dụng thực tế.

**Điểm cần nhớ:** `hasRole` **không tìm tên role trong bảng users**. Nó chỉ so khớp authority ở `Authentication`. Nếu có trường database `role="ADMIN"` nhưng user mapping tạo ra authority `ADMIN`, đường `/api/admin/**` sẽ bị từ chối theo mặc định.

### Khi nào chọn `hasRole`, khi nào chọn `hasAuthority`?

- Chọn `hasRole("ADMIN")` khi policy được mô tả theo **vai trò** và ứng dụng thống nhất quy ước `ROLE_`.
- Chọn `hasAuthority("invoice:approve")` khi policy theo **permission cụ thể**.
- Chọn `hasAuthority("ROLE_ADMIN")` nếu muốn so khớp chính xác chuỗi role authority và đã chủ ý dùng đầy đủ tiền tố.
- Chọn `hasAuthority("SCOPE_invoices.read")` khi kiểm tra **scope token đã ánh xạ**, nếu resource server sử dụng cấu hình mặc định tương ứng.
- Không chuyển bừa `hasRole("ADMIN")` sang `hasAuthority("ADMIN")` vì tưởng chúng “đều kiểm tra admin”.

## 8. Sử dụng trong method security

Bật method security bằng `@EnableMethodSecurity` trong cấu hình Spring. Có thể dùng `@PreAuthorize` trước method được Spring quản lý:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize("hasRole('ADMIN')")
public void resetApplicationSettings() {
    // Nghiệp vụ quản trị.
}

@PreAuthorize("hasAuthority('invoice:approve')")
public void approveInvoice(long invoiceId) {
    // Kiểm tra thêm invoice/tenant/trạng thái ở policy nghiệp vụ.
}

@PreAuthorize(
        "hasRole('ADMIN') or hasAuthority('invoice:read')")
public InvoiceDto readInvoice(long invoiceId) {
    // invoiceDto và chính sách thuộc ứng dụng thực tế.
}
~~~

Đây là **các method rời để minh họa annotation**, không phải một class độc lập có thể chạy ngay. Các method phải thuộc Spring-managed bean, method security đã được bật và lời gọi đi qua cơ chế intercept/proxy phù hợp. Một method trong cùng instance gọi nội bộ sang method khác có thể bỏ qua AOP advice, nên không giả định annotation luôn bảo vệ được self-invocation.

Expression có thể dùng `and`, `or` nhưng cần phân tích policy trước khi kết hợp: `or` có nghĩa là **chỉ cần một điều kiện đúng**. Nếu nghiệp vụ yêu cầu cả scope token lẫn permission nội bộ, hãy dùng `and` hoặc một policy bean đánh giá đủ các ràng buộc.

Ví dụ với permission và kiểm tra đối tượng:

~~~java
@PreAuthorize(
    "hasAuthority('invoice:read') " +
    "and @invoicePolicy.canRead(authentication, #invoiceId)"
)
public InvoiceDto findInvoice(long invoiceId) {
    return invoiceQueryService.findInvoice(invoiceId);
}
~~~

Đoạn trên chỉ hoạt động khi ứng dụng cung cấp bean `invoicePolicy`, `invoiceQueryService` và kiểu `InvoiceDto` phù hợp; tham số `#invoiceId` phải được nhận diện đúng qua metadata tham số hoặc cấu hình biên dịch. Không có phương thức `hasAuthority` hay `hasRole` nào **tự kiểm tra** rằng tài nguyên thuộc đúng tenant/owner.

### `@Secured` và `@RolesAllowed` không nên bị trộn quy ước

Có những ứng dụng còn dùng `@Secured` hoặc `@RolesAllowed` (JSR-250) sau khi bật hỗ trợ tương ứng. Chúng có cú pháp và cách xử lý role riêng. Không chuyển nguyên chuỗi từ `@PreAuthorize` sang annotation khác mà không kiểm tra tài liệu phiên bản đang dùng. Với bài học này, ưu tiên hiểu chắc `@PreAuthorize` và HTTP DSL trước.

## 9. Cơ chế tiền tố mặc định có thể được tùy chỉnh

Spring Security hỗ trợ cấu hình tiền tố mặc định cho kiểm tra role trong những cơ chế phù hợp. Ví dụ ở method security sử dụng `GrantedAuthorityDefaults`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.core.GrantedAuthorityDefaults;

@Configuration
public class RolePrefixConfig {

    @Bean
    static GrantedAuthorityDefaults grantedAuthorityDefaults() {
        return new GrantedAuthorityDefaults("APP_");
    }
}
~~~

Ý tưởng của cấu hình trên: trong các **expression handler** sử dụng `GrantedAuthorityDefaults` này, `hasRole('ADMIN')` được đánh giá theo tiền tố `APP_`, tức tìm `APP_ADMIN` thay vì `ROLE_ADMIN`.

**Tuy nhiên, không được suy ra mọi API đều đổi tiền tố chỉ vì bean đã tồn tại.** Một số cách tạo `AuthorizationManager` có cơ chế riêng. Chẳng hạn JavaDoc của `AuthorityAuthorizationManager.hasRole("ADMIN")` trong Spring Security 6.x quy định chuỗi được yêu cầu có tiền tố `ROLE_`; nếu muốn một authority tùy biến một cách tường minh, `hasAuthority("APP_ADMIN")` vẫn là cách xác định chính xác chuỗi. Các phiên bản mới hơn có thể cung cấp factory/cấu hình khác; phải kiểm tra đúng API và test hành vi thực tế của cả URL authorization lẫn method security.

Ngoài ra, thay tiền tố **không tự di chuyển dữ liệu**:

~~~text
Trước cấu hình:
  Authentication.authorities = ["ROLE_ADMIN"]
  hasRole("ADMIN") --> tìm "ROLE_ADMIN"

Sau khi đổi prefix trong cơ chế áp dụng:
  Authentication.authorities = ["ROLE_ADMIN"]   // vẫn là dữ liệu cũ
  hasRole("ADMIN") --> tìm "APP_ADMIN"          // không khớp

Để khớp, nguồn tạo Authentication cũng phải cấp "APP_ADMIN".
~~~

Khi đổi prefix, cần thống nhất toàn bộ: cách tạo user, mapper JWT, dữ liệu role, test helper, HTTP rule, method security, các custom managers và role hierarchy. Việc tự tùy biến tiền tố chỉ để “đỡ phải viết `ROLE_`” có thể tạo chi phí vận hành lớn; với ứng dụng thông thường, giữ chuẩn mặc định thường dễ đọc và dễ kiểm soát.

## 10. `ROLE_` khác `SCOPE_` và permission nghiệp vụ như thế nào?

Nhiều ứng dụng dùng OAuth 2.0 Resource Server JWT. Với converter mặc định thông dụng, scope từ claim `scope` hoặc `scp` được chuyển thành authority bắt đầu bằng `SCOPE_`.

Giả sử access token có:

~~~json
{
  "sub": "user-42",
  "scope": "invoices.read invoices.approve"
}
~~~

Authority được ánh xạ có thể là:

~~~text
SCOPE_invoices.read
SCOPE_invoices.approve
~~~

Khi đó:

~~~java
.hasAuthority("SCOPE_invoices.read")  // So khớp scope đã ánh xạ
.hasRole("ADMIN")                     // Không tự đúng chỉ vì token có scope
.hasAuthority("invoice:read")        // Không tự đúng chỉ vì token có SCOPE_invoices.read
~~~

**Những điều không được tự suy luận:**

- `SCOPE_invoices.read` không đồng nghĩa `ROLE_ADMIN`.
- `ROLE_ADMIN` không tự sinh `invoice:read`.
- `invoice:read` không tự chứng minh quyền đọc **mọi** hóa đơn trong tenant khác.
- Access token có scope không có nghĩa là quyền được cấp cho principal trong database hoặc IAM giống hệt.
- Spring Security JWT converter mặc định thường hiểu **scope**, không tự chuyển mọi claim `roles` tùy nhà cung cấp thành `ROLE_*`.

Nếu muốn đưa role/permission từ JWT thành authorities, hãy xác định rõ claim nào đáng tin, issuer/audience và cách ánh xạ; sau đó test nguyên quá trình xác minh token → tạo `Authentication` → đánh giá rule. Không được dùng token chưa được xác minh hoặc để client tự gán claim.

## 11. Role hierarchy không thay thế quy tắc tiền tố

Spring Security có thể hỗ trợ **role hierarchy**, ví dụ một cấu hình quy định `ROLE_ADMIN` có các authority mà `ROLE_USER` cũng được hưởng. Điều đó chỉ xảy ra nếu ứng dụng **đã cấu hình** hierarchy và bộ kiểm tra hiện tại thực sự sử dụng nó.

~~~text
Không cấu hình hierarchy:
  Authorities = ["ROLE_ADMIN"]
  hasRole("USER") --> false

Có hierarchy được áp dụng và khai báo ADMIN > USER:
  Authorities = ["ROLE_ADMIN"]
  hasRole("USER") --> có thể true theo hierarchy
~~~

Dấu `>` trong mô tả thể hiện quan hệ quyền do ứng dụng khai báo, không phải thứ được suy ra từ tên role. Khi hierarchy có mặt, `hasAuthority` cũng có thể được đánh giá trên các authorities có thể đạt tới theo cơ chế authorization cụ thể, vì vậy sự tương đương với thao tác `Set.contains` đơn giản cần được hiểu trong ngữ cảnh **không có hierarchy bổ sung**.

Thiết kế role hierarchy phải hạn chế việc vô tình cấp permission rộng hơn mong muốn. Một role quản trị tenant T1 không vì hierarchy mà mặc nhiên có quyền đối với tenant T2.

## 12. Ví dụ Java 17 độc lập: tự quan sát phép so khớp

Để nắm vững ý nghĩa của tiền tố, ví dụ dưới đây mô phỏng **quy tắc mặc định cơ bản** bằng Java thuần. Chương trình không dùng Spring Security và **không mô phỏng** cấu hình custom prefix hay role hierarchy; nó chỉ diễn tả vì sao `hasRole("ADMIN")` thường tương ứng với authority `ROLE_ADMIN`.

Lưu tệp `RolePrefixDemo.java`:

~~~java
import java.util.Set;

public class RolePrefixDemo {
    static boolean hasAuthority(Set<String> granted, String required) {
        return granted.contains(required);
    }

    static boolean hasRole(Set<String> granted, String roleName) {
        return hasAuthority(granted, "ROLE_" + roleName);
    }

    public static void main(String[] args) {
        Set<String> granted = Set.of(
                "ROLE_ADMIN",
                "invoice:read",
                "SCOPE_invoices.read"
        );

        System.out.println(
                "hasAuthority(ROLE_ADMIN): "
                + hasAuthority(granted, "ROLE_ADMIN"));

        System.out.println(
                "hasAuthority(ADMIN): "
                + hasAuthority(granted, "ADMIN"));

        System.out.println(
                "hasRole(ADMIN): "
                + hasRole(granted, "ADMIN"));

        System.out.println(
                "hasRole(USER): "
                + hasRole(granted, "USER"));

        System.out.println(
                "hasAuthority(invoice:read): "
                + hasAuthority(granted, "invoice:read"));

        System.out.println(
                "hasRole(invoice:read): "
                + hasRole(granted, "invoice:read"));

        System.out.println(
                "hasAuthority(SCOPE_invoices.read): "
                + hasAuthority(granted, "SCOPE_invoices.read"));
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac RolePrefixDemo.java
java RolePrefixDemo
~~~

Kết quả chuẩn:

~~~text
hasAuthority(ROLE_ADMIN): true
hasAuthority(ADMIN): false
hasRole(ADMIN): true
hasRole(USER): false
hasAuthority(invoice:read): true
hasRole(invoice:read): false
hasAuthority(SCOPE_invoices.read): true
~~~

Giải thích:

- `ROLE_ADMIN` đã được cấp nên so khớp chính xác thành công.
- `ADMIN` chưa được cấp nên `hasAuthority("ADMIN")` thất bại.
- `hasRole("ADMIN")` ghép tiền tố thành `ROLE_ADMIN`, nên thành công.
- `ROLE_USER` không có trong tập nên `hasRole("USER")` thất bại.
- `invoice:read` là authority đã được cấp nên `hasAuthority("invoice:read")` thành công.
- `hasRole("invoice:read")` lại tìm `ROLE_invoice:read` nên thất bại.
- `SCOPE_invoices.read` không cần `hasRole`; `hasAuthority` đã đủ để so khớp nguyên văn.

Trong ứng dụng thật, không nên tự viết lại `hasRole` như một policy thay Spring Security; chương trình chỉ giúp quan sát quy tắc mà không cần tải framework.

## 13. Test trong Spring Security: phát hiện nhầm tiền tố

Ví dụ kiểm thử HTTP với `Spring Security Test`, `MockMvc` và endpoint có rule `hasRole("ADMIN")`. Giả sử ứng dụng đã khai báo `GET /api/admin/ping` trả `200 OK` cho người được phép và đã bật security filter chain.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.test.context.support.WithMockUser;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RoleAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminRoleIsAccepted() throws Exception {
        mvc.perform(get("/api/admin/ping"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(authorities = "ROLE_ADMIN")
    void exactPrefixedAuthorityIsAccepted() throws Exception {
        mvc.perform(get("/api/admin/ping"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(authorities = "ADMIN")
    void RawAuthorityIsNotAnAdminRole() throws Exception {
        mvc.perform(get("/api/admin/ping"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "USER")
    void ordinaryUserIsForbidden() throws Exception {
        mvc.perform(get("/api/admin/ping"))
                .andExpect(status().isForbidden());
    }
}
~~~

**Điều kiện của ví dụ:** test class chỉ chạy khi dự án có endpoint `GET /api/admin/ping`, rule role phù hợp, dependencies Spring Boot Test/Spring Security Test và không có rule khác làm thay đổi quyết định. Nếu ứng dụng chưa có endpoint, phải tạo endpoint test hoặc chọn một endpoint admin hiện hữu; đoạn này là **mẫu test trong dự án**, không phải source Java độc lập.

Tên method test thứ ba dùng tên tự giải thích: authority `ADMIN` dạng thô **không** thỏa rule role `ADMIN` trong quy ước mặc định. Lưu ý Spring Security Test mô phỏng granted authorities, **không xác minh** quá trình tải roles từ database hay ánh xạ JWT; hãy bổ sung test integration cho luồng xác thực thật.

### Bộ tình huống test tối thiểu

| Tập authority của principal | Rule | Mong đợi |
|---|---|---|
| `ROLE_ADMIN` | `hasRole("ADMIN")` | Cho phép |
| `ADMIN` | `hasRole("ADMIN")` | Từ chối |
| `ROLE_ADMIN` | `hasAuthority("ROLE_ADMIN")` | Cho phép |
| `ROLE_ADMIN` | `hasAuthority("ADMIN")` | Từ chối |
| `invoice:read` | `hasAuthority("invoice:read")` | Cho phép |
| `ROLE_ADMIN` | `hasAuthority("invoice:read")` | Từ chối nếu không có mapping/hierarchy |
| `SCOPE_invoices.read` | `hasAuthority("SCOPE_invoices.read")` | Cho phép |
| `SCOPE_invoices.read` | `hasRole("ADMIN")` | Từ chối |

Bổ sung test cho tình huống không có authentication hoặc authentication không hợp lệ để xác minh luồng `401`/`403` đúng với entry point và handler của ứng dụng. Với ứng dụng đa tenant, tiếp tục test policy tài nguyên: qua được rule role không có nghĩa là được đọc mọi bản ghi.

## 14. Gỡ lỗi trường hợp “có role nhưng vẫn bị 403”

Thực hiện theo thứ tự kiểm tra, tránh đổi rule theo phỏng đoán:

1. **Xác nhận HTTP route/method**: request đang khớp matcher nào? Rule có bị matcher trước đó chặn không? Với method security, annotation trên method nào và interceptor có chạy không?
2. **Xác nhận authentication hợp lệ**: có principal tương ứng hay không? Đừng nhầm lỗi xác thực với lỗi thiếu quyền.
3. **Xem danh sách authority hiệu lực**: ví dụ dữ liệu an toàn đã được quan sát cho thấy `[ADMIN]` hay `[ROLE_ADMIN]`? Không log credential, access token đầy đủ hoặc thông tin nhạy cảm.
4. **Xác định rule đang yêu cầu gì**: `hasRole("ADMIN")` yêu cầu `ROLE_ADMIN` ở cấu hình mặc định, còn `hasAuthority("ADMIN")` yêu cầu `ADMIN`.
5. **Kiểm tra nơi cấp authority**: `UserDetailsService`, `AuthenticationProvider`, mapper database, JWT converter hoặc IdP có thêm/thiếu/nhân đôi tiền tố không?
6. **Kiểm tra custom prefix/hierarchy**: ứng dụng có `GrantedAuthorityDefaults`, custom authorization manager hoặc role hierarchy khiến kết quả khác dự kiến không?
7. **Kiểm tra các rule khác**: một request có thể vượt qua HTTP rule nhưng bị `@PreAuthorize`, ACL/object policy hoặc điều kiện nghiệp vụ từ chối.
8. **Khóa bằng test âm tính**: thêm test chứng minh principal chỉ có `ADMIN` phải bị từ chối nếu rule yêu cầu role `ADMIN` với prefix mặc định; test quyền đúng thì thành công.

Ví dụ lỗi thường gặp:

~~~text
Database role: ADMIN
          |
Mapping sai: new SimpleGrantedAuthority("ADMIN")
          |
Authentication authorities: [ADMIN]
          |
HTTP rule: hasRole("ADMIN")
          |
Required authority: ROLE_ADMIN
          |
Kết quả: từ chối
~~~

Cách sửa là **đồng bộ nguồn tạo authority và rule**. Có thể map role logic `ADMIN` thành `ROLE_ADMIN`, hoặc nếu hệ thống chủ ý dùng authority trần `ADMIN` thì kiểm tra bằng `hasAuthority("ADMIN")` và thống nhất convention; không sửa ngẫu nhiên từng endpoint để che lỗi mapping.

## 15. Những nhầm lẫn cần tránh

| Nhầm lẫn | Điều đúng |
|---|---|
| “`hasRole` đi truy vấn bảng role.” | `hasRole` kiểm tra authorities đã gắn vào `Authentication` theo quy ước tiền tố. |
| “`hasAuthority("ADMIN")` giống `hasRole("ADMIN")`.” | Mặc định, một bên đòi `ADMIN`, bên kia đòi `ROLE_ADMIN`. |
| “`hasAuthority` cũng tự thêm `ROLE_`.” | `hasAuthority` so khớp authority được truyền nguyên văn. |
| “Truyền `ROLE_ADMIN` vào `hasRole` luôn được/luôn lỗi.” | Hành vi phụ thuộc API và cơ chế expression; chọn `hasRole("ADMIN")` để nhất quán. |
| “Có role ADMIN thì chắc chắn có mọi permission.” | Chỉ có các authorities/mapping/hierarchy được định nghĩa mới được áp dụng. |
| “Đã đổi prefix thì dữ liệu trong `Authentication` cũng tự đổi.” | Quy tắc so khớp thay đổi, nguồn tạo authority cần đồng bộ riêng. |
| “Mock user roles đúng là JWT converter cũng đúng.” | Test mock bypass nhiều bước xác thực; phải test converter/claims riêng. |
| “OAuth scope là role.” | `SCOPE_*` và `ROLE_*` thường là hai quy ước khác nhau, không tự suy ra nhau. |
| “Có `ROLE_ADMIN` là được xem mọi tài nguyên.” | Function-level role chưa thay thế kiểm tra object-level, tenant/owner và điều kiện nghiệp vụ. |

## 16. Quy tắc sử dụng trong code review

Trước khi merge một thay đổi về phân quyền, kiểm tra:

- **Contract authority:** chính xác những chuỗi nào được gắn vào `Authentication`? Ví dụ `ROLE_ACCOUNTANT`, `invoice:read` hay `SCOPE_invoices.read`.
- **Nguồn cấp:** database/IAM/JWT/LDAP nào chịu trách nhiệm, dữ liệu đã được xác thực chưa?
- **API gọi:** `hasRole` nhận tên role logic; `hasAuthority` nhận chuỗi authority đầy đủ.
- **Prefix:** `ROLE_` mặc định hay tiền tố đã cấu hình? Cấu hình có được áp dụng ở cả HTTP/method authorization không?
- **Permission vs role:** endpoint cần một chức danh hay một permission hành động cụ thể?
- **Quyền trên đối tượng:** có cần check tenant, owner, trạng thái tài nguyên, hay chính sách chia sẻ không?
- **Test:** có cả ca allow và deny với authority bị thiếu tiền tố, thừa tiền tố và sai tên không?

Nếu dự án cần một convention đơn giản, có thể quy định: **roles lưu ở tầng nghiệp vụ như `ADMIN`; khi tạo `Authentication` ánh xạ thành `ROLE_ADMIN`; gọi `hasRole("ADMIN")` cho role, gọi `hasAuthority("invoice:read")` cho permission, và `hasAuthority("SCOPE_invoices.read")` cho scope đã ánh xạ**. Đây là một phương án thiết kế nhất quán, không phải quy định bắt buộc của Spring Security.

## 17. Tự kiểm tra kiến thức

**Câu 1.** Người dùng chỉ có authority `ADMIN`. `hasRole("ADMIN")` có cho qua theo mặc định không?  
**Không**. Nó yêu cầu `ROLE_ADMIN`.

**Câu 2.** Người dùng chỉ có authority `ROLE_ADMIN`. `hasAuthority("ADMIN")` có cho qua không?  
**Không**. `hasAuthority` so khớp đúng chuỗi và không thêm tiền tố.

**Câu 3.** Muốn kiểm tra role ADMIN bằng Spring Security HTTP DSL mặc định thì viết gì?  
**`hasRole("ADMIN")`**. Một cách tường minh khác là `hasAuthority("ROLE_ADMIN")`.

**Câu 4.** `.roles("ADMIN")` trong `UserDetails` builder thường tạo authority nào?  
**`ROLE_ADMIN`**.

**Câu 5.** `@WithMockUser(authorities = "ADMIN")` có tương đương `@WithMockUser(roles = "ADMIN")` không?  
**Không**: một bên tạo `ADMIN`, bên còn lại tạo `ROLE_ADMIN`.

**Câu 6.** Có authority `SCOPE_invoices.read` có mặc nhiên thỏa `hasAuthority("invoice:read")` không?  
**Không**. Hai chuỗi không trùng và policy không tự suy luận mapping.

**Câu 7.** Sau khi cấu hình prefix thành `APP_` trong một expression handler, `hasRole('ADMIN')` yêu cầu gì?  
**`APP_ADMIN`** trong expression handler thực sự áp dụng cấu hình đó. Hãy kiểm tra riêng các authorization manager khác.

**Câu 8.** Vì sao không khẳng định `hasRole("ROLE_ADMIN")` luôn lỗi?  
Vì **có khác biệt giữa Java `AuthorityAuthorizationManager.hasRole` và một số SpEL `SecurityExpressionRoot.hasRole`**. Cách viết có thể chuyển đổi, dễ hiểu nhất vẫn là `hasRole("ADMIN")`.

**Câu 9.** Khi authority trong authentication là `ROLE_ADMIN` nhưng yêu cầu vẫn bị từ chối, có chắc `hasRole("ADMIN")` sai không?  
**Không**. Cần kiểm tra matcher, rule khác, prefix tùy chỉnh, method security, role hierarchy, chính sách đối tượng và luồng xác thực.

### Tài liệu chính thức

- Spring Security – Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security – Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security – Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security 6.5 – `AuthorityAuthorizationManager` JavaDoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorityAuthorizationManager.html
- Spring Security 6.5 – `SecurityExpressionRoot` JavaDoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/expression/SecurityExpressionRoot.html

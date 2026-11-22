# Phân biệt tên vai trò nghiệp vụ với authority trong ứng dụng

Trong một hệ thống bán hàng, người dùng có thể được gọi là **“Quản lý cửa hàng”**, được lưu trong cơ sở dữ liệu với mã vai trò `STORE_MANAGER`, rồi được Spring Security nhận diện bằng `ROLE_STORE_MANAGER`. Cả ba cách gọi có liên quan nhưng **không phải ba giá trị có thể thay thế tùy ý cho nhau**. Nếu trộn lẫn nhãn hiển thị, mã vai trò nghiệp vụ và authority mà framework thực sự kiểm tra, ứng dụng dễ gặp lỗi “đăng nhập được nhưng bị 403”, cấp sai quyền, hoặc bỏ sót ranh giới giữa các cửa hàng.

Bài học tập trung vào việc xác định ý nghĩa của từng tên, hiểu cơ chế `GrantedAuthority`, `hasRole`/`hasAuthority`, chuyển đổi từ role nghiệp vụ sang authority một cách có kiểm soát, và kiểm thử phép ánh xạ đó trong Spring Security.

## 1. Ba tầng tên thường bị nhầm

Hãy xét cùng một người có vai trò quản lý cửa hàng:

| Tầng | Giá trị ví dụ | Nguồn và mục đích |
| --- | --- | --- |
| **Nhãn hiển thị** | `Quản lý cửa hàng` | Văn bản giao diện; có thể dịch sang ngôn ngữ khác và thay đổi cách viết. |
| **Mã role nghiệp vụ** | `STORE_MANAGER` | Khái niệm ổn định do hệ thống nghiệp vụ định nghĩa; thường nằm trong enum, bảng role hoặc bảng phân công. |
| **GrantedAuthority của Spring** | `ROLE_STORE_MANAGER` | Chuỗi authority được gắn vào `Authentication` để các bộ kiểm tra quyền của Spring Security đối chiếu. |
| **Authority cho thao tác cụ thể** | `ORDER_VIEW`, `ORDER_APPROVE` | Quyền hành động mà ứng dụng quyết định cấp; không nhất thiết là role. |

**Nhãn hiển thị không phải khóa phân quyền.** Hôm nay giao diện dùng “Quản lý cửa hàng”, ngày mai đổi thành “Cửa hàng trưởng” hoặc “Store Manager”; việc đổi bản dịch không được vô tình làm thay đổi quyền. Luôn dựa vào mã ổn định, không so sánh các chuỗi giao diện như `hasAuthority("Quản lý cửa hàng")`.

**Mã role nghiệp vụ không tự trở thành authority.** Một bản ghi `role_code = STORE_MANAGER` trong database chỉ là dữ liệu ứng dụng. Spring Security không tự truy vấn bảng đó, cũng không mặc nhiên gắn tiền tố `ROLE_` khi lưu hoặc lấy dữ liệu. Ứng dụng cần tự quyết định khi xác thực sẽ chuyển các vai trò/quyền đáng tin cậy thành những `GrantedAuthority` nào.

**Authority là cách biểu diễn quyền mà Spring Security nhận được.** `Authentication.getAuthorities()` trả tập hợp các `GrantedAuthority`; mỗi authority phổ biến có một chuỗi từ `getAuthority()`. Ví dụ cả `ROLE_STORE_MANAGER` và `ORDER_APPROVE` đều có thể được biểu diễn bằng `SimpleGrantedAuthority`. Spring Security không tự suy ra ý nghĩa nghiệp vụ từ chuỗi `ORDER_APPROVE`; ứng dụng phải xác định nó cho phép hành động nào.

Nói cách khác:

~~~text
Nhãn UI ("Quản lý cửa hàng")
       |
       | hiển thị tên tương ứng, không cấp quyền
       v
Role nghiệp vụ (STORE_MANAGER)
       |
       | ánh xạ theo quy tắc ứng dụng, sau khi xác minh người dùng
       v
GrantedAuthority ("ROLE_STORE_MANAGER", "ORDER_VIEW", "ORDER_APPROVE")
       |
       | được AuthorizationManager / method security sử dụng
       v
Quyết định truy cập (ALLOW / DENY)
       |
       + điều kiện dữ liệu: cửa hàng, chủ sở hữu, trạng thái, hạn mức...
~~~

Đường mũi tên giữa role và authority là **một phép ánh xạ phải được thiết kế**, không phải định luật của framework. Hai ứng dụng có thể định nghĩa role `STORE_MANAGER` giống nhau nhưng cấp các permission hoàn toàn khác nhau.

## 2. Cơ chế `hasRole` và `hasAuthority`: khác ở cách so khớp

Trong cấu hình Spring Security thông thường, role được biểu diễn dưới dạng authority có tiền tố **`ROLE_`**. Các bộ kiểm tra chuẩn sử dụng những quy ước sau:

| Biểu thức | Authority được kiểm tra khi dùng tiền tố role mặc định | Ý nghĩa |
| --- | --- | --- |
| `hasRole("STORE_MANAGER")` | `ROLE_STORE_MANAGER` | Kiểm tra role theo quy ước tiền tố. |
| `hasAuthority("ROLE_STORE_MANAGER")` | `ROLE_STORE_MANAGER` | Kiểm tra đúng chuỗi authority. |
| `hasAuthority("STORE_MANAGER")` | `STORE_MANAGER` | Kiểm tra đúng chuỗi, **không tự thêm** `ROLE_`. |
| `hasAuthority("ORDER_APPROVE")` | `ORDER_APPROVE` | Kiểm tra quyền thao tác, không thêm tiền tố role. |
| `hasAnyRole("STORE_MANAGER", "SUPPORT")` | Một trong `ROLE_STORE_MANAGER`, `ROLE_SUPPORT` | Kiểm tra nhiều role. |
| `hasAnyAuthority("ORDER_VIEW", "ORDER_APPROVE")` | Một trong hai chuỗi nguyên văn | Kiểm tra nhiều authority. |

Ví dụ người gọi có:

~~~text
Authentication.authorities = [
  "ROLE_STORE_MANAGER",
  "ORDER_VIEW",
  "ORDER_APPROVE"
]
~~~

Khi dùng cấu hình tiền tố mặc định:

- `hasRole("STORE_MANAGER")` → **true**.
- `hasAuthority("ROLE_STORE_MANAGER")` → **true**.
- `hasAuthority("STORE_MANAGER")` → **false**.
- `hasAuthority("ORDER_APPROVE")` → **true**.
- `hasRole("ORDER_APPROVE")` → **false**, vì phép kiểm tra role tìm `ROLE_ORDER_APPROVE`, không phải `ORDER_APPROVE`.

Đặc biệt, không viết `hasRole("ROLE_STORE_MANAGER")` theo thói quen **tự thêm tiền tố vào tham số role**. Trong các API mặc định, `hasRole` vốn đã xử lý tiền tố và có thể từ chối tham số được thêm `ROLE_` từ trước; hãy truyền mã `STORE_MANAGER` vào `hasRole`, hoặc truyền chuỗi đầy đủ vào `hasAuthority`.

Quy tắc `ROLE_` là **quy ước có thể cấu hình** ở một số thành phần, chẳng hạn qua `GrantedAuthorityDefaults`. Một hệ thống đã thay đổi tiền tố phải dùng quy ước nhất quán và có test cho cả HTTP authorization lẫn method security; không nên thay tiền tố chỉ để chữa lỗi ánh xạ dữ liệu. Phân biệt rõ **role code** (thuộc domain) và **role authority** (thuộc Spring) giúp tránh ảnh hưởng chéo khi cấu hình đổi.

Chuỗi authority được so sánh **chính xác**; `STORE_MANAGER`, `store_manager` và `Store_Manager` là những giá trị khác nhau. Nếu dữ liệu từ nhiều nguồn, hãy chuẩn hóa từ phía máy chủ tại một điểm ánh xạ tin cậy và kiểm thử dữ liệu bất thường. Đừng tự động biến mọi chuỗi do client cung cấp thành `ROLE_<value>`.

## 3. Role nghiệp vụ được lưu trong database khác authority ở thời điểm xác thực

Một mô hình dữ liệu minh họa:

~~~text
users
  id | username
  17 | alice

business_roles
  code           | display_name_vi
  STORE_MANAGER  | Quản lý cửa hàng
  SALES_ASSISTANT| Nhân viên bán hàng

store_role_assignments
  user_id | store_id | role_code
  17      | store-7  | STORE_MANAGER
~~~

Bảng `store_role_assignments` nói rằng **Alice là quản lý của `store-7`**. Nó không có nghĩa Alice được mang role quản lý ở mọi cửa hàng. Nếu chỉ đưa `ROLE_STORE_MANAGER` vào một tập authority phẳng mà bỏ mất `store_id`, application có nguy cơ coi Alice là quản lý ở `store-9` khi một endpoint chỉ kiểm tra `hasRole("STORE_MANAGER")`.

Một luồng thông thường:

1. Người dùng được xác thực bằng session, username/password hoặc token đã xác minh.
2. Server lấy mã role, permission và phạm vi áp dụng từ kho dữ liệu/quy tắc cấp quyền đáng tin cậy.
3. Một lớp **mapper** chuyển các mã có hiệu lực thành `GrantedAuthority`, ví dụ `STORE_MANAGER` thành `ROLE_STORE_MANAGER`, `ORDER_APPROVE` thành `ORDER_APPROVE`.
4. Spring Security lưu các authority đó trong `Authentication`, nơi các bộ kiểm tra có thể sử dụng.
5. Khi truy cập **bản ghi cụ thể**, service vẫn kiểm tra tenant/store, quyền sở hữu, trạng thái hoặc các điều kiện mà authority không đủ mô tả.

Khi sử dụng `UserDetailsService`, ứng dụng cần trả `UserDetails` với các authority đã ánh xạ. Với OAuth2 Resource Server dùng JWT, authority có thể được tạo từ JWT bằng converter riêng hoặc cấu hình mặc định; **không có chuyện mọi claim có tên `roles` đều tự động trở thành `ROLE_...`**. Cấu hình mặc định của `JwtGrantedAuthoritiesConverter` thường ánh xạ scope của token sang authority dạng `SCOPE_<scope>` (chẳng hạn `scope=orders.read` thành `SCOPE_orders.read`), chứ không tự biến nó thành `ROLE_STORE_MANAGER`.

Một role từ hệ thống danh tính bên ngoài cần có **hợp đồng ánh xạ rõ ràng**: claim nào chứa role, issuer/audience nào được tin, giá trị nào được chấp nhận, role mang phạm vi tenant nào, và liệu role đó có được ứng dụng cấp permission tương ứng hay không. Nhận một chuỗi `ADMIN` từ request header tự khai rồi tạo `ROLE_ADMIN` là lỗi cấp quyền.

## 4. Mapping role → authority và permission một cách có chủ đích

Giả sử miền bán hàng có hai role:

| Business role | Authority role | Permission ứng dụng có thể cấp |
| --- | --- | --- |
| `STORE_MANAGER` | `ROLE_STORE_MANAGER` | `ORDER_VIEW`, `ORDER_APPROVE`. |
| `SALES_ASSISTANT` | `ROLE_SALES_ASSISTANT` | `ORDER_VIEW`. |

Đây là **chính sách minh họa**, không phải đặc tính mặc định của Spring Security. Khi cấp quyền thật, nên có một nguồn ánh xạ duy nhất: cấu hình được kiểm soát, bảng role-permission có quản trị thay đổi, hoặc mã chính sách nghiệp vụ. Không hard-code quyền lặp lại ở controller, service, mapper và giao diện khiến chúng dễ lệch nhau.

Cầu nối với Spring Security có thể dùng `SimpleGrantedAuthority`:

~~~java
import java.util.HashSet;
import java.util.Set;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class BusinessAuthorityMapper {
    public static Set<GrantedAuthority> map(
            Set<String> businessRoleCodes,
            Set<String> grantedPermissions) {
        Set<GrantedAuthority> result = new HashSet<>();

        for (String roleCode : businessRoleCodes) {
            // roleCode phải đến từ tập mã role tin cậy do server quản lý.
            result.add(new SimpleGrantedAuthority("ROLE_" + roleCode));
        }
        for (String permission : grantedPermissions) {
            // Permission cũng phải được cấp từ nguồn tin cậy.
            result.add(new SimpleGrantedAuthority(permission));
        }
        return Set.copyOf(result);
    }

    private BusinessAuthorityMapper() {}
}
~~~

Đây là **lớp minh họa cần thư viện Spring Security trong classpath**, không phải file có thể chạy độc lập bằng `java`. Ứng dụng thật còn phải chặn/chuẩn hóa mã không hợp lệ; riêng hàm trên **không nên được gọi bằng các tập vai trò do client tự gửi**. Nếu cơ sở dữ liệu đã lưu `ROLE_STORE_MANAGER`, phải quy định rõ có bỏ tiền tố trước khi map hay không, tránh tạo chuỗi `ROLE_ROLE_STORE_MANAGER`. Thông thường dễ quản trị hơn khi **role code của domain không chứa tiền tố `ROLE_`**, và mapper chịu trách nhiệm về quy ước framework.

Có hai cách cấp permission phổ biến, cần chọn một cách thống nhất:

- **Từ role:** role `STORE_MANAGER` được định nghĩa cấp `ORDER_VIEW` và `ORDER_APPROVE`. Lúc xác thực, mapper mở rộng role thành các permission authority.
- **Được cấp riêng:** cùng role `STORE_MANAGER` nhưng chỉ một số người được cấp thêm `ORDER_APPROVE` sau khi được đào tạo/phê duyệt. Mapper lấy role và permission hiệu lực từ dữ liệu phân quyền riêng.

Trong cả hai cách, **việc có role authority không ngầm sinh ra permission authority** nếu ứng dụng chưa thực hiện phép ánh xạ. Ví dụ, `hasAuthority("ORDER_APPROVE")` không tự thành true chỉ vì người gọi có `ROLE_STORE_MANAGER`.

Một số hệ thống định nghĩa **role hierarchy** (ví dụ `ROLE_ADMIN` bao hàm `ROLE_STORE_MANAGER`). Nếu dùng cơ chế này, hãy cấu hình có chủ đích và kiểm thử quy tắc mở rộng quyền; đừng xem hierarchy như mặc định của Spring. Role hierarchy cũng không thay thế kiểm tra bản ghi và tenant.

## 5. Ví dụ Java 17+ chạy độc lập: nhìn rõ hai không gian tên

Chương trình sau **không cần Spring**; nó mô phỏng cơ chế role nghiệp vụ được đổi thành chuỗi authority và cách một quyết định còn phụ thuộc dữ liệu của đơn hàng. Nhờ vậy có thể kiểm tra bản chất ánh xạ mà không bị nhiễu bởi cấu hình filter hoặc proxy.

Lưu chính xác thành **BusinessRoleAuthorityDemo.java**:

~~~java
import java.util.HashSet;
import java.util.Set;

public class BusinessRoleAuthorityDemo {
    enum BusinessRole { STORE_MANAGER, SALES_ASSISTANT }

    record User(String id, String storeId, Set<BusinessRole> businessRoles) {}
    record Order(String storeId, boolean awaitingApproval) {}

    static Set<String> authoritiesFor(Set<BusinessRole> roles) {
        Set<String> result = new HashSet<>();
        for (BusinessRole role : roles) {
            result.add("ROLE_" + role.name());
            switch (role) {
                case STORE_MANAGER -> {
                    result.add("ORDER_VIEW");
                    result.add("ORDER_APPROVE");
                }
                case SALES_ASSISTANT -> result.add("ORDER_VIEW");
            }
        }
        return Set.copyOf(result);
    }

    static boolean hasRole(Set<String> authorities, String role) {
        return authorities.contains("ROLE_" + role);
    }

    static boolean hasAuthority(Set<String> authorities, String authority) {
        return authorities.contains(authority);
    }

    static boolean canApprove(User user, Order order) {
        Set<String> authorities = authoritiesFor(user.businessRoles());
        return authorities.contains("ORDER_APPROVE")
                && user.storeId().equals(order.storeId())
                && order.awaitingApproval();
    }

    public static void main(String[] args) {
        User manager = new User("u17", "store-7",
                Set.of(BusinessRole.STORE_MANAGER));
        User assistant = new User("u28", "store-7",
                Set.of(BusinessRole.SALES_ASSISTANT));
        Set<String> managerAuthorities =
                authoritiesFor(manager.businessRoles());
        Set<String> assistantAuthorities =
                authoritiesFor(assistant.businessRoles());

        System.out.println("Business role: "
                + BusinessRole.STORE_MANAGER.name());
        System.out.println("Role authority: "
                + hasRole(managerAuthorities, "STORE_MANAGER"));
        System.out.println("Raw role name as authority: "
                + hasAuthority(managerAuthorities, "STORE_MANAGER"));
        System.out.println("Manager approve permission: "
                + hasAuthority(managerAuthorities, "ORDER_APPROVE"));
        System.out.println("Assistant approve permission: "
                + hasAuthority(assistantAuthorities, "ORDER_APPROVE"));
        System.out.println("Same-store pending order: "
                + canApprove(manager, new Order("store-7", true)));
        System.out.println("Other-store pending order: "
                + canApprove(manager, new Order("store-9", true)));
        System.out.println("Same-store completed order: "
                + canApprove(manager, new Order("store-7", false)));
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac BusinessRoleAuthorityDemo.java
java BusinessRoleAuthorityDemo
~~~

Kết quả chính xác:

~~~text
Business role: STORE_MANAGER
Role authority: true
Raw role name as authority: false
Manager approve permission: true
Assistant approve permission: false
Same-store pending order: true
Other-store pending order: false
Same-store completed order: false
~~~

**Giải thích từng điểm then chốt:**

- `BusinessRole.STORE_MANAGER.name()` trả **`STORE_MANAGER`**, mã nghiệp vụ không mang tiền tố.
- Mapper thêm `ROLE_` để tạo **`ROLE_STORE_MANAGER`**; vì vậy ví dụ `hasRole(..., "STORE_MANAGER")` thành true.
- `hasAuthority(..., "STORE_MANAGER")` thành false vì tập authority **không chứa chuỗi nguyên văn** `STORE_MANAGER`.
- `ORDER_APPROVE` là một authority về **thao tác**, chỉ được cấp do quy tắc gán permission riêng của ví dụ.
- Có `ORDER_APPROVE` vẫn chưa đủ để phê duyệt mọi đơn. `canApprove` cần đúng `storeId` và đơn đang chờ duyệt. Hai kết quả cuối là false dù manager vẫn có cùng authority.

Trong chương trình, tập role được dựng thủ công để minh họa. Khi triển khai thật, role phải đến từ assignment đã kiểm chứng; `storeId` của người gọi phải gắn với ngữ cảnh tin cậy, và trạng thái đơn phải lấy từ dữ liệu mới nhất. Không lấy role/authority từ payload rồi xem như đã được cấp.

## 6. Sử dụng trong Spring Security: kiểm tra đúng loại tên

### Tầng HTTP

Đây là **đoạn cấu hình đặt trong ứng dụng Spring Boot có dependency Spring Security**, không phải chương trình độc lập (bổ sung các import cho `@Configuration`, `@Bean`, `HttpSecurity`, `SecurityFilterChain`):

~~~java
@Configuration
class WebAuthorizationConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/backoffice/**").hasRole("STORE_MANAGER")
            .requestMatchers("/api/orders/**").authenticated()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
~~~

`hasRole("STORE_MANAGER")` tìm **`ROLE_STORE_MANAGER`** theo tiền tố mặc định. Nếu bộ xác thực tạo authority `STORE_MANAGER` không có tiền tố, một quản lý hợp lệ vẫn bị từ chối ở nhánh này. Nếu nhầm đặt `hasAuthority("STORE_MANAGER")` trong khi thực tế tạo `ROLE_STORE_MANAGER`, kết quả cũng không khớp.

Ngược lại, `authenticated()` cho `/api/orders/**` chỉ yêu cầu có người dùng đã xác thực; nó **không kiểm tra quyền sửa, chủ sở hữu hoặc cửa hàng**. Trên API có dữ liệu nhiều cửa hàng, lớp nghiệp vụ phải kiểm tra `order.storeId` với phạm vi người gọi đã được xác minh.

### Tầng phương thức

Có thể bật `@EnableMethodSecurity` trong cấu hình, rồi áp dụng biểu thức:

~~~java
@PreAuthorize("hasRole('STORE_MANAGER') and hasAuthority('ORDER_APPROVE')")
public void approveOrder(long orderId) {
    // Service tải đơn từ server và kiểm tra storeId, trạng thái,
    // người được phân công và các điều kiện nghiệp vụ khác.
}
~~~

Đây là **phương thức minh họa** trong một Spring bean, không phải lớp chạy độc lập. `@PreAuthorize` chỉ kiểm tra role và permission hiện có trong `Authentication`. Dòng chú thích phải được thay bằng logic thực thi trên bản ghi thật; nếu bỏ kiểm tra đó, quản lý cửa hàng này có thể thử duyệt đơn của cửa hàng khác.

Hãy phân biệt hai hợp đồng nghiệp vụ:

- Nếu **có permission `ORDER_APPROVE` là đủ điều kiện chức năng**, dùng `hasAuthority('ORDER_APPROVE')` rồi xét dữ liệu đơn; không ép thêm role nếu ứng dụng có thể cấp permission hợp lệ cho vai trò mới.
- Nếu **bắt buộc vừa là quản lý cửa hàng vừa có quyền duyệt**, dùng biểu thức kết hợp như trên. Khi đổi mô hình tổ chức, cập nhật và kiểm thử hợp đồng trước khi sửa annotation.

Method security trong Spring dựa trên AOP proxy. Lời gọi nội bộ từ một phương thức sang phương thức khác trên **cùng instance** có thể bỏ qua interceptor. Vì vậy các ràng buộc bất biến theo dữ liệu (tenant, owner, trạng thái) cần được bảo đảm nhất quán tại tầng service/policy và trong giao dịch cập nhật, thay vì chỉ trông chờ annotation ở controller.

### Khi mapper tạo đối tượng `GrantedAuthority`

Nếu đã có một tập role và permission đã được kiểm chứng, việc tạo:

~~~java
new SimpleGrantedAuthority("ROLE_STORE_MANAGER")
new SimpleGrantedAuthority("ORDER_APPROVE")
~~~

tương ứng với hai authority **riêng biệt**. Hàm kiểm tra `hasRole` sử dụng authority đầu; `hasAuthority("ORDER_APPROVE")` dùng authority sau. Đừng nhầm tham số `hasRole("STORE_MANAGER")` với cú pháp constructor của `SimpleGrantedAuthority`: constructor nhận **toàn bộ chuỗi authority**, không tự thêm `ROLE_`.

## 7. So sánh nguồn danh tính và cách framework xây dựng authority

Tên authority trong ứng dụng phụ thuộc **cách bạn tạo `Authentication`**, không chỉ dựa vào tên cột database.

| Nguồn | Giá trị nguồn | Authority có thể thấy trong Spring | Điểm cần kiểm chứng |
| --- | --- | --- | --- |
| Database role nội bộ | `STORE_MANAGER` | `ROLE_STORE_MANAGER` nếu mapper tự thêm tiền tố | Có mapper và nguồn role đáng tin hay chưa? |
| Database permission | `ORDER_APPROVE` | `ORDER_APPROVE` nếu mapper tạo đúng giá trị | Ai cấp permission, có thời hạn/phạm vi không? |
| `UserDetails` | Danh sách `GrantedAuthority` do ứng dụng trả về | Đúng các chuỗi đã tạo | Có dùng `roles(...)` hay `authorities(...)` khi tạo user? |
| JWT scope mặc định | `orders.read` trong `scope`/`scp` | Thường là `SCOPE_orders.read` | Có converter tùy biến không? Scope có phải permission nghiệp vụ không? |
| JWT claim role tùy biến | `roles: ["STORE_MANAGER"]` | Chỉ có role authority nếu ứng dụng **ánh xạ** claim đó | Issuer có đáng tin, converter có đúng, tenant nào áp dụng? |

Trong builder của Spring Security, `roles("STORE_MANAGER")` (khi dùng mặc định) tạo authority có `ROLE_`; còn `authorities("STORE_MANAGER")` biểu thị chuỗi nguyên văn, không coi đó là role. Khi mock trong test, `@WithMockUser(roles = "STORE_MANAGER")` tạo `ROLE_STORE_MANAGER`; `@WithMockUser(authorities = "STORE_MANAGER")` tạo `STORE_MANAGER`. Đây là nguồn gây ra nhiều ca test “pass nhưng hệ thống thật trả 403” nếu dữ liệu test và mapper sản xuất không thống nhất.

Với JWT, một token có `scope=orders.read` **không đồng nghĩa** có `ROLE_STORE_MANAGER`. Sử dụng `hasAuthority('SCOPE_orders.read')` có thể là đúng khi nguồn authority là scope đã xác thực và API được thiết kế theo scope đó. Nếu chính sách dựa trên role nghiệp vụ, phải định nghĩa converter/nguồn cấp role riêng và kiểm tra phạm vi tenant.

Một người có thể được phân nhiều role tại những tổ chức khác nhau. Có hai hướng triển khai thông dụng: chọn tổ chức đang hoạt động từ ngữ cảnh đã xác minh rồi tạo authority có hiệu lực cho phạm vi đó; hoặc giữ bảng phân công role theo tổ chức và xét membership khi truy cập từng tài nguyên. Dù chọn cách nào, **role authority phẳng không tự mã hóa phạm vi dữ liệu**.

## 8. Vì sao 403 xuất hiện dù database có role?

Xét một cuộc điều tra cụ thể:

1. Database cho thấy `role_code = STORE_MANAGER`.
2. Người dùng đăng nhập thành công.
3. Endpoint kiểm tra `hasRole('STORE_MANAGER')`.
4. API trả 403.

Đừng lập tức bỏ điều kiện `hasRole` hay thêm `permitAll`. Hãy kiểm chứng tuần tự:

| Điều cần nhìn | Ví dụ đúng | Sai lệch thường gặp |
| --- | --- | --- |
| Role nghiệp vụ đã được cấp cho **đúng người và đúng phạm vi** chưa? | `user=17, store=store-7, role=STORE_MANAGER` | Role chỉ thuộc store khác hoặc assignment hết hiệu lực. |
| Mapper đã đọc role hợp lệ chưa? | Lấy `STORE_MANAGER` từ nguồn tin cậy | Mapper bỏ sót role hoặc đọc nhầm bảng. |
| `Authentication.getAuthorities()` hiện có gì? | `ROLE_STORE_MANAGER` | Chỉ có `STORE_MANAGER`, `SCOPE_...` hoặc tập rỗng. |
| Điều kiện đang kiểm tra gì? | `hasRole('STORE_MANAGER')` | `hasAuthority('STORE_MANAGER')` nhưng chỉ có `ROLE_STORE_MANAGER`. |
| Phạm vi dữ liệu có hợp lệ không? | Người dùng thuộc store của đơn | Có role đúng nhưng khác tenant, trạng thái cấm. |
| Quyền có bị thay đổi sau khi đăng nhập không? | Quyền trong session/token vẫn hợp lệ | Quyền được thêm nhưng session cũ chưa cập nhật, hoặc bị thu hồi nhưng token cũ còn quyền. |

Một authority có thể được gắn vào `Authentication` ở thời điểm xác thực và tồn tại cho đến khi session được làm mới hoặc token hết hạn. Nếu quyền thay đổi thường xuyên hoặc phải bị thu hồi ngay, cần thiết kế làm mới quyền, tra cứu tại thời điểm yêu cầu hoặc cơ chế phiên/token phù hợp. Đừng “chữa” vấn đề cache quyền bằng cách chấp nhận tùy ý role do frontend gửi.

Khi ghi log hỗ trợ debug, chỉ ghi các mã quyền/phạm vi cần thiết, người dùng đã được xác minh và lý do từ chối ở mức thích hợp. Không in password, access token, cookie hay các claim nhạy cảm. Phản hồi API cũng không nên vô tình tiết lộ bản ghi của tenant khác chỉ vì người gọi có role đúng.

## 9. Những lỗi thiết kế thường gặp

1. **Dùng nhãn UI làm mã bảo mật.** Thay chữ “Quản lý cửa hàng” trong bản dịch khiến role-check hỏng. → Dùng mã domain ổn định, label chỉ để hiển thị.
2. **Tưởng database tự cấp quyền cho Spring.** Có role trong bảng nhưng `Authentication.getAuthorities()` không chứa role tương ứng. → Định nghĩa và kiểm thử mapper.
3. **Tự thêm `ROLE_` ở cả dữ liệu lẫn mapper.** Sinh ra `ROLE_ROLE_STORE_MANAGER`. → Thống nhất một quy ước mã nguồn và một điểm chuyển đổi.
4. **Nhầm `hasRole` với `hasAuthority`.** `hasAuthority('STORE_MANAGER')` không khớp `ROLE_STORE_MANAGER`. → So sánh với chuỗi authority thực tế.
5. **Đồng nhất role với permission.** `ROLE_STORE_MANAGER` không đồng nghĩa `ORDER_APPROVE` nếu hệ thống chưa định nghĩa quan hệ cấp quyền. → Map permission có chủ đích.
6. **Dùng role chung cho mọi tenant.** Một người quản lý ở store-7 vô tình quản lý được store-9. → Bảo vệ phạm vi theo store/tenant tại tầng dữ liệu.
7. **Tin role/scope do client tự nhập.** Cho phép nâng quyền từ body/header. → Chỉ sử dụng danh tính/claim đã được xác minh và quyền từ nguồn server tin cậy.
8. **Quá phụ thuộc vào `@PreAuthorize`.** Một lời gọi nội bộ né proxy hoặc thao tác trên bản ghi không được kiểm tra trạng thái. → Giữ bất biến trong service/policy và test nhiều đường gọi.
9. **Test với role khác cách production gắn authority.** Test pass nhưng người dùng thật 403. → Tái sử dụng quy tắc mapping hoặc assert tập authority sản xuất.
10. **Dựa vào authority snapshot quá cũ.** Quyền bị thu hồi nhưng token còn sống. → Cân nhắc hiệu lực phiên/token và cơ chế thu hồi khi mức rủi ro đòi hỏi.

## 10. Kiểm thử đúng không gian tên và phạm vi

Nên viết kiểm thử ở **hai tầng**: (a) mapper chuyển role nghiệp vụ sang authority, (b) chính sách dùng authority cùng điều kiện tài nguyên.

Bảng ca cơ bản:

| Đầu vào hoặc ngữ cảnh | Kiểm tra | Kỳ vọng |
| --- | --- | --- |
| Role nghiệp vụ `STORE_MANAGER` | Mapper sinh `ROLE_STORE_MANAGER` | Có. |
| Role nghiệp vụ `STORE_MANAGER` | Mapper sinh `STORE_MANAGER` không tiền tố | Không, nếu không cấp thêm có chủ đích. |
| `ROLE_STORE_MANAGER` có trong Authentication | `hasRole('STORE_MANAGER')` | ALLOW tại lớp role. |
| Chỉ có `STORE_MANAGER` | `hasRole('STORE_MANAGER')` | DENY với mặc định. |
| Chỉ có `ROLE_STORE_MANAGER` | `hasAuthority('STORE_MANAGER')` | DENY. |
| Có `ORDER_VIEW` nhưng thiếu `ORDER_APPROVE` | Quyền duyệt | DENY. |
| Có `ROLE_STORE_MANAGER` và `ORDER_APPROVE`, đúng store | Đơn còn chờ duyệt | Có thể ALLOW nếu toàn bộ điều kiện nghiệp vụ đúng. |
| Cùng authority nhưng đơn thuộc store khác | Duyệt đơn khác store | DENY. |
| JWT chỉ có `SCOPE_orders.read` | `hasRole('STORE_MANAGER')` | DENY nếu không có thêm role authority. |
| Mock user với `roles = "STORE_MANAGER"` | Tập authority | Phải có `ROLE_STORE_MANAGER`. |
| Mock user với `authorities = "STORE_MANAGER"` | Tập authority | Chỉ có `STORE_MANAGER` theo khai báo. |

Trong Spring Security Test, `@WithMockUser` tiện cho kiểm thử `hasRole`/`hasAuthority`; với resource server JWT, cần test security context/converter theo cấu hình token thực tế. Kiểm thử mapper ở mức unit test sẽ phát hiện lỗi biến `STORE_MANAGER` thành `ROLE_ROLE_STORE_MANAGER` hoặc bỏ quên permission. Integration test cần kiểm tra trả về 403 khi không đủ quyền và ranh giới tenant ngay cả khi role chính xác.

Một ca quan trọng là **đổi tên hiển thị**: cập nhật `display_name_vi` từ “Quản lý cửa hàng” thành “Cửa hàng trưởng” trong dữ liệu UI, nhưng mã `STORE_MANAGER`, authority `ROLE_STORE_MANAGER` và kết quả kiểm tra phải **giữ nguyên**. Ca này chứng minh tên hiển thị không chi phối logic bảo mật.

## 11. Quy trình đặt tên và ánh xạ đáng tin cậy

Với một role mới, chẳng hạn “Nhân viên đối soát”, có thể theo quy trình:

1. Đặt **mã nghiệp vụ ổn định** như `RECONCILIATION_STAFF` và nhãn hiển thị tiếng Việt độc lập.
2. Định nghĩa rõ role được cấp ở phạm vi nào: toàn hệ thống, tenant, cửa hàng, dự án.
3. Định nghĩa permission thực sự cần, ví dụ `RECONCILIATION_READ`; không mặc định cho quyền duyệt hay xuất dữ liệu.
4. Ở một mapper được kiểm soát, chuyển role thành `ROLE_RECONCILIATION_STAFF` và permission thành authority nguyên văn.
5. Cấu hình `hasRole('RECONCILIATION_STAFF')` khi **nhóm vai trò** là điều kiện nghiệp vụ; `hasAuthority('RECONCILIATION_READ')` khi cần kiểm tra **thao tác**.
6. Thực thi điều kiện tài nguyên ở server, gồm phạm vi tenant, phân công, trạng thái và yêu cầu phê duyệt khác nếu có.
7. Kiểm tra ca ALLOW và DENY ở cả mapper, method/HTTP và tầng dữ liệu. Ghi rõ cách quyền được làm mới khi assignment thay đổi.

**Điểm cần nhớ:** Role nghiệp vụ là tên của trách nhiệm trong domain; `GrantedAuthority` là biểu diễn quyền cụ thể đưa vào Spring Security. Chuỗi `ROLE_` mang ý nghĩa quy ước kiểm tra role, không biến một nhãn hiển thị hoặc một hàng database thành quyền một cách tự động. Thiết kế rõ **mã role → mapper → authority → chính sách + điều kiện tài nguyên** giúp đổi tên hiển thị an toàn, xử lý lỗi 403 chính xác và tránh cấp nhầm quyền giữa các phạm vi dữ liệu.

### Tài liệu tham khảo

- [Spring Security – Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)

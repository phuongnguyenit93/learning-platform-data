# Kiểm thử quyền trực tiếp, quyền suy ra và thay đổi hierarchy trong Spring Security

## 1. Mục tiêu và tình huống thực tế

Ứng dụng quản lý báo cáo có bốn role:

- `ROLE_ADMIN`: quản trị viên.
- `ROLE_MANAGER`: quản lý nhóm.
- `ROLE_ANALYST`: người phân tích.
- `ROLE_VIEWER`: người chỉ xem.

Chính sách ban đầu quy định quản trị viên được thực hiện mọi chức năng của manager, manager được làm việc của analyst, và analyst được xem như viewer. Một số role còn **suy ra permission** nghiệp vụ: analyst được đọc báo cáo; manager được phê duyệt báo cáo.

Nhóm phát triển thay đổi quy tắc: **bỏ quyền duyệt suy ra từ ROLE_MANAGER**, nhưng vẫn muốn người được cấp trực tiếp `report:approve` tiếp tục duyệt được. Nếu chỉ test việc admin mở trang thành công, sự khác biệt này rất dễ bị bỏ sót.

Bài học tập trung vào **kiểm thử** chứ không chỉ cấu hình `RoleHierarchy`. Kết thúc bài, bạn có thể:

1. Phân biệt chính xác **direct authorities** và **reachable/inherited authorities**.
2. Hiểu chiều và tính bắc cầu của phép `ROLE_A > ROLE_B`.
3. Viết unit test `RoleHierarchy.getReachableGrantedAuthorities(...)` có cả trường hợp tích cực và tiêu cực.
4. Kiểm thử việc hierarchy được dùng đúng ở HTTP authorization và method security.
5. Phân biệt `@WithMockUser(roles=...)` với `@WithMockUser(authorities=...)`.
6. Đánh giá tác động khi **thêm, xóa, đảo chiều hoặc thay đổi hierarchy**.
7. Kiểm thử thu hồi quyền, JWT/session cũ, cấu hình đang chạy và đối tượng thuộc tenant khác.
8. Dùng ma trận regression và chặn leo thang quyền ngoài chủ đích trước khi triển khai.

**Phạm vi kỹ thuật:** Spring Security Servlet, Java 17+, `RoleHierarchyImpl`, `SecurityFilterChain`, `@EnableMethodSecurity`, JUnit 5 và Spring Security Test. Ví dụ có chú thích *fragment* cần đặt trong project Spring Boot có dependencies và controller/service phù hợp; phần Java 17 thuần ở cuối là chương trình độc lập.

## 2. Mô hình: authority trực tiếp khác authority suy ra

### 2.1. Tập quyền nguồn D và tập quyền hiệu lực R(D)

Giả sử tại thời điểm xác thực, một `Authentication` có:

```text
Direct authorities D:
    ROLE_MANAGER
```

Role hierarchy mô tả:

```text
ROLE_ADMIN   > ROLE_MANAGER
ROLE_MANAGER > ROLE_ANALYST
ROLE_ANALYST > ROLE_VIEWER

ROLE_MANAGER > report:approve
ROLE_ANALYST > report:read
```

Dấu `>` nghĩa là role/authority bên trái **bao hàm** bên phải, không phải phép so sánh số và không phải “vai trò bên phải cao hơn”. Với source `ROLE_MANAGER`, hệ thống có thể suy ra:

```text
Reachable authorities R(D):
    ROLE_MANAGER       (trực tiếp)
    ROLE_ANALYST       (suy ra)
    ROLE_VIEWER        (suy ra theo hai bước)
    report:approve     (suy ra)
    report:read        (suy ra thông qua ROLE_ANALYST)
```

**Tập direct vẫn có mặt trong tập reachable.** Theo contract của `RoleHierarchy`, `getReachableGrantedAuthorities(...)` trả về authorities được gán trực tiếp **và** tất cả authorities có thể đạt tới theo quan hệ bắc cầu.

Có thể hình dung:

```text
ROLE_ADMIN
    │
    ▼
ROLE_MANAGER ──────► report:approve
    │
    ▼
ROLE_ANALYST ──────► report:read
    │
    ▼
ROLE_VIEWER
```

Mũi tên **chỉ một chiều**. Từ `ROLE_VIEWER` **không** thể suy ngược `ROLE_ANALYST`, `ROLE_MANAGER` hay `ROLE_ADMIN`.

### 2.2. Công thức và ý nghĩa kiểm thử

Đặt:

- `D` = tập authority được nguồn xác thực cấp trực tiếp.
- `H` = đồ thị hierarchy được cấu hình.
- `R_H(D)` = tập reachable authorities dưới hierarchy `H`, gồm `D`.
- `I_H(D) = R_H(D) \ D` = tập authority **chỉ có do suy ra**.

Một rule yêu cầu authority `a` có thể cho phép khi `a ∈ R_H(D)`, **nếu bộ kiểm tra authorization thực sự sử dụng RoleHierarchy H**. Không phải mọi đoạn code đọc `Authentication.getAuthorities()` đều tự mở rộng theo hierarchy.

Vì vậy, một test tốt phải tách ba khẳng định:

1. `Authentication.getAuthorities()` phản ánh **quyền được gán từ nguồn xác thực/test fixture**.
2. `RoleHierarchy.getReachableGrantedAuthorities(...)` thực hiện closure theo graph.
3. HTTP/method authorization tích hợp hierarchy có hoặc không **dựa trên closure đó** để đánh giá quyền.

**Không dùng kết quả của bước 2 để tự kết luận bước 3 đã được cấu hình đúng.**

### 2.3. Vì sao role hierarchy không phải object authorization?

`ROLE_MANAGER > report:approve` có thể làm người có role MANAGER thỏa điều kiện chức năng `hasAuthority("report:approve")`. Nhưng báo cáo `r7` có thể thuộc tenant khác, đã khóa hoặc đang chờ hai người duyệt. Hierarchy không biết owner, tenant, trạng thái hay người tạo báo cáo. Những rule đó phải do method/domain authorization thực thi riêng.

## 3. Cấu hình baseline cho bài kiểm thử

### 3.1. Bean RoleHierarchyImpl

Một cấu hình đơn giản, dùng API `fromHierarchy` của Spring Security hiện đại:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;

@Configuration
public class HierarchyConfiguration {

    @Bean
    static RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy("""
                ROLE_ADMIN > ROLE_MANAGER
                ROLE_MANAGER > ROLE_ANALYST
                ROLE_ANALYST > ROLE_VIEWER
                ROLE_MANAGER > report:approve
                ROLE_ANALYST > report:read
                """);
    }
}
```

Đây là class cấu hình **trong một project Spring Boot**. Chuỗi truyền vào định nghĩa từng quan hệ `authority nguồn > authority được suy ra`; `report:read` và `report:approve` là **permission strings** được quy định bởi ứng dụng, không phải tên class hay quyền có sẵn.

`RoleHierarchyImpl.fromHierarchy(...)` thuận tiện khi muốn mô tả toàn bộ graph bằng text. Các phiên bản mới khuyến nghị dùng nó thay cho constructor rỗng và `setHierarchy(...)` cũ vốn đã bị deprecate.

### 3.2. Builder kiểu role ở Spring Security 6.3+

Khi hierarchy chỉ có role theo quy ước prefix `ROLE_`, có thể dùng:

```java
RoleHierarchy hierarchy = RoleHierarchyImpl.withDefaultRolePrefix()
        .role("ADMIN").implies("MANAGER")
        .role("MANAGER").implies("ANALYST")
        .role("ANALYST").implies("VIEWER")
        .build();
```

`withDefaultRolePrefix()` và `withRolePrefix(String)` xuất hiện từ Spring Security **6.3**. Với baseline có thêm permission `report:read` và `report:approve`, ví dụ `fromHierarchy` rõ ràng hơn để tránh nhầm chuyện builder áp dụng prefix cho những tên role.

**Lưu ý:** cú pháp `ROLE_` là convention mặc định; `hasRole("MANAGER")` thường tra `ROLE_MANAGER`. `hasAuthority("ROLE_MANAGER")` tra đúng chuỗi đã ghi. Nếu hệ thống đổi prefix, phải đồng bộ nguồn authorities, builder, HTTP và method security. Đừng chỉ đổi một chỗ rồi cho rằng hierarchy đã hoạt động toàn bộ.

### 3.3. Không biến mọi quyền thành role chỉ vì có dấu >

Hierarchy có thể nối các chuỗi authority, ví dụ:

```text
ROLE_ANALYST > report:read
```

nhưng `report:read` **không** vì vậy mà trở thành `ROLE_report:read`. Test nên kiểm tra đúng `hasAuthority("report:read")`. Một quy tắc HTTP `hasRole("report:read")` sẽ theo prefix mặc định đòi `ROLE_report:read` và không tương đương.

Đặt tên rõ:

```text
ROLE_ADMIN          = role
ROLE_MANAGER        = role
ROLE_ANALYST        = role
ROLE_VIEWER         = role
report:read         = permission
report:approve      = permission
```

Với JWT, scope như `reports.read` thường được converter mặc định ánh xạ thành `SCOPE_reports.read`, **không tự bằng** `report:read`. Nếu nguồn xác thực có JWT scopes, thống nhất ánh xạ trước khi kiểm thử hierarchy.

## 4. Ma trận quyền nguồn và quyền suy ra

Với hierarchy baseline `H0`:

| Direct D | ROLE_VIEWER | ROLE_ANALYST | ROLE_MANAGER | ROLE_ADMIN | report:read | report:approve |
| --- | --- | --- | --- | --- | --- | --- |
| `ROLE_ADMIN` | Suy ra | Suy ra | Suy ra | **Trực tiếp** | Suy ra | Suy ra |
| `ROLE_MANAGER` | Suy ra | Suy ra | **Trực tiếp** | Không | Suy ra | Suy ra |
| `ROLE_ANALYST` | Suy ra | **Trực tiếp** | Không | Không | Suy ra | Không |
| `ROLE_VIEWER` | **Trực tiếp** | Không | Không | Không | Không | Không |
| `ROLE_SUPPORT` | Không | Không | Không | Không | Không | Không |
| `report:read` | Không | Không | Không | Không | **Trực tiếp** | Không |
| `ROLE_VIEWER` + `report:approve` | **Trực tiếp** | Không | Không | Không | Không | **Trực tiếp** |

Ở đây “Không” nghĩa là không thuộc reachable set dưới **H0** từ direct set đã ghi. Nó không có nghĩa không thể có quyền đó theo một cơ chế độc lập khác.

Điều gì cần kiểm thử?

- **Tính bắc cầu:** ADMIN suy ra VIEWER dù không có cạnh trực tiếp ADMIN→VIEWER.
- **Không suy ngược:** VIEWER không suy ra ADMIN.
- **Độc lập giữa roles và permissions:** người có `report:read` trực tiếp không tự nhận `ROLE_ANALYST`.
- **Không bị giới hạn ở role:** `ROLE_MANAGER` suy ra cả `report:approve`.
- **Gộp nhiều nguồn:** direct có nhiều authority thì reachable là phần hợp nhất closure của tất cả.
- **Không cấp quyền ngoài graph:** ROLE_SUPPORT không nhận quyền report nếu không được cấu hình.

**Test quyết định:** phải có ít nhất một người **chỉ có role cao**, một người **chỉ có role thấp**, một người có **permission trực tiếp** và một người **hoàn toàn không liên quan**.

## 5. Unit test RoleHierarchy.getReachableGrantedAuthorities

### 5.1. Test closure, không kiểm tra thứ tự trả về

Mẫu JUnit 5 + AssertJ, đặt trong project có `spring-security-core`, JUnit và AssertJ:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

class RoleHierarchyUnitTest {

    private final RoleHierarchy hierarchy =
            RoleHierarchyImpl.fromHierarchy("""
                    ROLE_ADMIN > ROLE_MANAGER
                    ROLE_MANAGER > ROLE_ANALYST
                    ROLE_ANALYST > ROLE_VIEWER
                    ROLE_MANAGER > report:approve
                    ROLE_ANALYST > report:read
                    """);

    private Set<String> reachable(String... direct) {
        var authorities = java.util.Arrays.stream(direct)
                .map(SimpleGrantedAuthority::new)
                .toList();

        return hierarchy.getReachableGrantedAuthorities(authorities)
                .stream()
                .map(GrantedAuthority::getAuthority)
                .collect(Collectors.toSet());
    }

    @Test
    void adminIncludesDirectAndTransitiveAuthorities() {
        assertThat(reachable("ROLE_ADMIN")).containsExactlyInAnyOrder(
                "ROLE_ADMIN",
                "ROLE_MANAGER",
                "ROLE_ANALYST",
                "ROLE_VIEWER",
                "report:read",
                "report:approve");
    }

    @Test
    void analystDoesNotGainManagerOrApprove() {
        assertThat(reachable("ROLE_ANALYST"))
                .containsExactlyInAnyOrder(
                        "ROLE_ANALYST", "ROLE_VIEWER", "report:read");
    }

    @Test
    void directPermissionDoesNotImplyRole() {
        assertThat(reachable("report:read"))
                .containsExactlyInAnyOrder("report:read");
    }

    @Test
    void multipleDirectAuthoritiesAreCombined() {
        assertThat(reachable("ROLE_VIEWER", "report:approve"))
                .containsExactlyInAnyOrder(
                        "ROLE_VIEWER", "report:approve");
    }

    @Test
    void unrelatedRoleDoesNotGetReportRights() {
        assertThat(reachable("ROLE_SUPPORT"))
                .containsExactlyInAnyOrder("ROLE_SUPPORT");
    }
}
```

Dùng `containsExactlyInAnyOrder` vì `RoleHierarchy` trả `Collection`, không hứa thứ tự chính xác. Cách kiểm tra bằng `Set<String>` loại vấn đề thứ tự và giúp diễn đạt contract của tập quyền.

### 5.2. Đừng chỉ kiểm “có quyền” mà bỏ kiểm “không có quyền”

Một test `ROLE_ADMIN` có `ROLE_VIEWER` vẫn pass nếu ai đó vô tình thêm:

```text
ROLE_VIEWER > report:approve
```

và khiến người chỉ xem được phê duyệt. Vì vậy cần **negative assertions** cho từng role thấp:

```java
@Test
void viewerCannotApprove() {
    assertThat(reachable("ROLE_VIEWER"))
            .doesNotContain("report:approve", "ROLE_ADMIN");
}
```

Test role hierarchy là dạng **kiểm thử an ninh**; negative cases quan trọng không kém positive cases.

### 5.3. Chứng minh direct và inferred là hai tập khác

```java
@Test
void directIsNotAutomaticallyExpandedInAuthentication() {
    var raw = Set.of("ROLE_MANAGER");
    var expanded = reachable("ROLE_MANAGER");

    assertThat(raw).containsExactly("ROLE_MANAGER");
    assertThat(expanded).contains(
            "ROLE_MANAGER", "ROLE_ANALYST",
            "ROLE_VIEWER", "report:read", "report:approve");
}
```

Đoạn trên so sánh raw set giả lập nguồn và expanded set; để kiểm tra `Authentication` thật, tạo `UsernamePasswordAuthenticationToken` hoặc dùng `@WithMockUser`, rồi đọc `getAuthorities()` trên principal test. Đừng dùng code ví dụ này để khẳng định mọi Authentication provider đều luôn lưu mỗi role một cách giống nhau.

## 6. Vì sao @WithMockUser không chứng minh hierarchy đang được áp dụng?

### 6.1. @WithMockUser(roles=...) thiết lập direct roles

Ví dụ:

```java
@WithMockUser(roles = "MANAGER")
```

thường tạo `Authentication` trong test với direct authority:

```text
ROLE_MANAGER
```

Nó **không tự chèn** `ROLE_ANALYST`, `ROLE_VIEWER`, `report:approve`, `report:read` vào `Authentication.getAuthorities()`. Những authorities suy ra phải được `RoleHierarchy` tính ở **bộ kiểm tra quyền đã tích hợp hierarchy**.

Ngược lại:

```java
@WithMockUser(authorities = "report:approve")
```

cấp đúng direct permission `report:approve`. Đây là test quan trọng để xác minh thay đổi hierarchy không vô tình tước quyền **được cấp trực tiếp**.

### 6.2. Hai assertion khác nhau có thể đồng thời đúng

Với user `ROLE_MANAGER`:

```text
authentication.getAuthorities():
    [ROLE_MANAGER]

roleHierarchy.getReachableGrantedAuthorities(...):
    [ROLE_MANAGER, ROLE_ANALYST, ROLE_VIEWER,
     report:approve, report:read]
```

Cả hai đều đúng. Nếu một custom service tự viết:

```java
boolean allowed = authentication.getAuthorities()
        .stream()
        .anyMatch(a -> a.getAuthority().equals("report:read"));
```

nó có thể trả `false` cho manager mặc dù `@PreAuthorize("hasAuthority('report:read')")` trong hệ thống đã tích hợp RoleHierarchy có thể cho phép. Custom code đó đang chỉ so sánh direct authorities, **không hỏi hierarchy**.

**Không chọn một trong hai hành vi theo trực giác:** hãy định rõ chính sách dùng direct hay effective authorities và test đúng component. Nếu cần cùng ngữ nghĩa, hãy dùng `AuthorizationManager`/`RoleHierarchy` được cấu hình nhất quán.

### 6.3. Test chỉ cấp đúng quyền nguồn

Không nên làm:

```java
@WithMockUser(authorities = {
    "ROLE_MANAGER", "ROLE_ANALYST",
    "ROLE_VIEWER", "report:approve", "report:read"
})
```

rồi kết luận hierarchy hoạt động vì method đọc báo cáo pass. Test đó **đã tự cấp mọi quyền suy ra bằng tay**; nếu hierarchy bị xóa hoàn toàn, test vẫn có thể pass.

Để test suy ra, **chỉ cấp direct role**:

```java
@WithMockUser(roles = "MANAGER")
```

và assert endpoint/method yêu cầu `report:read` hoặc `report:approve` đạt trong môi trường đã đăng ký hierarchy.

## 7. Kiểm thử HTTP authorization với RoleHierarchy

### 7.1. Bắt đầu từ manager có setRoleHierarchy tường minh

Ở Spring Security **6.5**, `AuthorityAuthorizationManager` có `setRoleHierarchy(RoleHierarchy)`. Dùng explicit manager giúp test rõ có hay không việc áp dụng hierarchy, thay vì dựa vào một cấu hình global không rõ hoạt động.

Ví dụ class cấu hình tích hợp:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
public class ReportHttpSecurityConfig {

    @Bean
    SecurityFilterChain reportChain(HttpSecurity http,
                                    RoleHierarchy roleHierarchy)
            throws Exception {

        AuthorityAuthorizationManager<RequestAuthorizationContext> read =
                AuthorityAuthorizationManager.hasAuthority("report:read");
        read.setRoleHierarchy(roleHierarchy);

        AuthorityAuthorizationManager<RequestAuthorizationContext> approve =
                AuthorityAuthorizationManager.hasAuthority("report:approve");
        approve.setRoleHierarchy(roleHierarchy);

        return http.authorizeHttpRequests(auth -> auth
                .requestMatchers(
                        HttpMethod.GET, "/api/reports", "/api/reports/*")
                    .access(read)
                .requestMatchers(
                        HttpMethod.POST, "/api/reports/*/approve")
                    .access(approve)
                .anyRequest().denyAll()
        ).build();
    }
}
```

**Đây là class Spring Security Servlet cần đặt trong project có authentication provider, controllers và bean `RoleHierarchy` ở mục 3**. Ví dụ không tự cung cấp login/session/JWT hay CSRF configuration. Với request POST, nếu CSRF đang bật, test phải gửi token hợp lệ để không nhầm 403 CSRF với từ chối bởi hierarchy.

`AuthorityAuthorizationManager` với `setRoleHierarchy(...)` là API có sẵn ở dòng 6.5; các dòng mới có thêm cơ chế factory quản lý hierarchy. Khi copy code cho Spring Security 7+, đối chiếu Javadoc phiên bản và ưu tiên cấu hình được tài liệu dòng đó khuyến nghị.

### 7.2. Vì sao không chỉ dùng hasRole("MANAGER") cho mọi route?

Một API có thể cần **permission** chứ không phải vai trò:

- `GET /api/reports/r7` yêu cầu `report:read`.
- `POST /api/reports/r7/approve` yêu cầu `report:approve`.
- `GET /api/admin/users` yêu cầu `ROLE_ADMIN`.

Role hierarchy cho phép role cao suy ra permission phù hợp, nhưng chỉ khi **authorization manager đang sử dụng hierarchy**. Một `hasRole("MANAGER")` ở HTTP và `hasAuthority("report:read")` ở method có thể biểu diễn hai chính sách bổ sung; không được coi chúng luôn tương đương nếu graph thay đổi.

### 7.3. Ma trận HTTP quan trọng

| Principal test (direct) | GET /api/reports/r7 | POST /api/reports/r7/approve |
| --- | --- | --- |
| `ROLE_ADMIN` | Cho phép qua HTTP rule | Cho phép qua HTTP rule |
| `ROLE_MANAGER` | Cho phép (suy ra) | Cho phép (suy ra) |
| `ROLE_ANALYST` | Cho phép (suy ra) | Từ chối |
| `ROLE_VIEWER` | Từ chối | Từ chối |
| `ROLE_SUPPORT` | Từ chối | Từ chối |
| `report:read` | Cho phép (direct) | Từ chối |
| `report:approve` | Từ chối | Cho phép (direct) |

Bảng là kết quả **của hierarchy H0 và manager ở mục 7.1**. Controller/service vẫn có thể từ chối vì report không tồn tại, tenant khác hoặc trạng thái report không hợp lệ.

### 7.4. MockMvc integration test theo rule

Ví dụ fragment trong `@SpringBootTest` + `@AutoConfigureMockMvc`, có controller test trả status thành công:

```java
@Test
@WithMockUser(roles = "MANAGER")
void managerCanReadThroughInheritedPermission() throws Exception {
    mockMvc.perform(get("/api/reports/r7"))
            .andExpect(status().isOk());
}

@Test
@WithMockUser(roles = "ANALYST")
void analystCannotApprove() throws Exception {
    mockMvc.perform(post("/api/reports/r7/approve").with(csrf()))
            .andExpect(status().isForbidden());
}

@Test
@WithMockUser(authorities = "report:approve")
void directlyGrantedPermissionCanApprove() throws Exception {
    mockMvc.perform(post("/api/reports/r7/approve").with(csrf()))
            .andExpect(status().isOk());
}
```

**Lưu ý quan trọng:** những test kỳ vọng `200` **chỉ** đúng nếu có handler test thực sự tồn tại, fixture `r7` được phép, method/service không chặn thêm và controller trả 200. Nếu API trả 204 hoặc 202, dùng assertion tương ứng. Với `@WebMvcTest`, cần import security configuration/RoleHierarchy bean vào test slice; nếu thiếu thì không được coi test pass/fail là hành vi production.

Các snippet trên không phải file test độc lập; cần thêm các imports, bean injection `MockMvc` và test class đúng context.

### 7.5. Test admin không bị mở quyền ngược

Thêm endpoint:

```java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

và kiểm tra với `ROLE_MANAGER`, `ROLE_ANALYST`, `ROLE_VIEWER` đều bị từ chối. Tuy nhiên, nếu chỉ gắn matcher admin sau `/api/**.authenticated()` thì rule có thể bị che bởi matcher rộng; cần test **thứ tự first-match** chứ không chỉ test một manager đơn lẻ.

## 8. Method security: test @PreAuthorize và handler thực sự dùng hierarchy

### 8.1. Bật và cấu hình ở đúng nơi

Spring Security hỗ trợ kiểm tra theo method như:

```java
@PreAuthorize("hasAuthority('report:read')")
public ReportView view(String reportId) {
    return reportRepository.loadVisible(reportId);
}
```

Muốn `ROLE_ANALYST` tự đáp ứng `report:read` qua hierarchy, `MethodSecurityExpressionHandler` sử dụng cho `@PreAuthorize` phải được cấu hình có `RoleHierarchy` tương ứng.

Theo tài liệu Spring Security, có thể thêm:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class ReportMethodSecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            RoleHierarchy roleHierarchy) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setRoleHierarchy(roleHierarchy);
        return handler;
    }
}
```

Dòng `static @Bean` tương ứng với hướng dẫn Spring Security để handler được đăng ký đúng lúc khi method-security infrastructure khởi tạo. Cấu hình này cần bean `RoleHierarchy` từ mục 3. Nếu ứng dụng dùng cơ chế factory hoặc các method annotations khác (như `@Secured`, JSR-250), phải kiểm chứng wiring theo dòng phiên bản và annotation cụ thể.

### 8.2. Test invocation qua Spring proxy

Ví dụ Spring-managed service:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportPolicyProbe {

    @PreAuthorize("hasAuthority('report:read')")
    public String read() {
        return "read-ok";
    }

    @PreAuthorize("hasAuthority('report:approve')")
    public String approve() {
        return "approve-ok";
    }
}
```

Test bean này **bằng cách inject từ Spring context** và gọi method qua proxy:

```java
@Test
@WithMockUser(roles = "ANALYST")
void analystReadsWithInheritedPermission() {
    assertThat(reportPolicyProbe.read()).isEqualTo("read-ok");
    assertThatThrownBy(() -> reportPolicyProbe.approve())
            .isInstanceOf(AccessDeniedException.class);
}
```

Đây là fragment cần `@SpringBootTest` hoặc method-security test context tương ứng, AssertJ, `AccessDeniedException` và injected `ReportPolicyProbe`. Trong phương thức service thật, còn phải check quyền theo object và tenant.

**Self-invocation:** gọi `this.read()` từ method khác trong cùng object có thể không đi qua method-security proxy, làm test cho kết quả sai. Test nên gọi **bean đã được proxy** từ bên ngoài.

### 8.3. Khi HTTP pass mà method fail

Một người có `ROLE_MANAGER` gọi GET /api/reports/r7:

1. HTTP manager đã `setRoleHierarchy` → thấy `report:read` suy ra → cho qua.
2. Method handler **chưa setRoleHierarchy** → chỉ thấy direct `ROLE_MANAGER` → `hasAuthority('report:read')` thất bại.

Đây là lỗi cấu hình **không đồng bộ giữa HTTP và method security**, không phải role hierarchy không hoạt động. Test bắt buộc đi qua cả hai lớp mới phát hiện được.

Ngược lại, chỉ test method mà không test HTTP route có thể bỏ sót matcher/chain không bảo vệ endpoint phù hợp.

## 9. Phân biệt unit test, policy integration test và end-to-end test

| Tầng test | Điều chứng minh | Điều **không** tự chứng minh |
| --- | --- | --- |
| Unit test `RoleHierarchyImpl` | Đồ thị H sinh tập reachable đúng | HTTP/method interceptor dùng H |
| Test `AuthorityAuthorizationManager` | Manager dùng H để grant/deny permission | Route matcher/Servlet chain được chọn đúng |
| Test `@PreAuthorize` qua Spring context | Method-security handler thực sự kiểm tra H | HTTP URL được bảo vệ |
| MockMvc + Spring Security | Filter chain/matcher/authentication và handler theo test setup | Gateway, JWT converter production nếu test mock |
| Integration HTTP với token/session thật | Auth provider/converter + security + controller hợp tác | Mọi race/role revocation dài hạn hoặc mọi tenant |
| Regression test khi đổi H | Quyền hiệu lực biến đổi đúng delta | Chính sách data/object-level nếu không kiểm |

Một bộ test chất lượng nên có **đủ nhiều tầng**, không cần mỗi tầng lặp lại toàn bộ ca, nhưng phải có ít nhất một luồng thành công và một luồng bị từ chối đi qua cấu hình Spring thực.

### 9.1. Tránh test tautology

Test dễ mắc:

```java
var hierarchy = RoleHierarchyImpl.fromHierarchy(
        "ROLE_MANAGER > report:approve");
var expanded = hierarchy.getReachableGrantedAuthorities(
        List.of(new SimpleGrantedAuthority("ROLE_MANAGER")));

assertThat(expanded).isNotEmpty();
```

Assertion `isNotEmpty` yếu: chỉ cần giữ direct ROLE_MANAGER cũng đủ pass, ngay cả khi cạnh `report:approve` bị sai. Test phải assert **toàn tập hoặc quyền đích cụ thể**, cùng các quyền **không được** nhận.

### 9.2. Test security là contract, không phải ảnh chụp setup

Cần phân biệt:

- “ROLE_MANAGER **phải** duyệt được trong baseline.”
- “ROLE_MANAGER **không còn** duyệt được sau change request.”
- “Người có permission `report:approve` **trực tiếp** vẫn được duyệt.”
- “ROLE_VIEWER **không bao giờ** tự trở thành admin.”

Đây là business contract. Test chỉ kiểm snapshot của một config file mà không mô tả mong muốn rất dễ bị cập nhật assertion theo bug.

## 10. Thay đổi hierarchy: xác định delta trước khi đổi code

### 10.1. Hai phiên bản H0 và H1

Hierarchy ban đầu H0:

```text
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_ANALYST
ROLE_ANALYST > ROLE_VIEWER
ROLE_MANAGER > report:approve
ROLE_ANALYST > report:read
```

Business thay đổi: **manager không còn tự động được duyệt**. Hierarchy H1:

```text
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_ANALYST
ROLE_ANALYST > ROLE_VIEWER
ROLE_ANALYST > report:read
```

Ở H1, cạnh `ROLE_MANAGER > report:approve` bị xóa. Vì không còn đường khác tới `report:approve`, người chỉ có `ROLE_MANAGER` và `ROLE_ADMIN` đều **mất quyền approve suy ra**. Điều này dễ bất ngờ: ADMIN cao hơn MANAGER nên cũng mất permission đó nếu không có một cạnh khác.

### 10.2. Ma trận thay đổi quyền phải xét cả quyền bắc cầu

| Direct principal | report:read H0 → H1 | report:approve H0 → H1 | Ý nghĩa |
| --- | --- | --- | --- |
| `ROLE_ADMIN` | ALLOW → ALLOW | **ALLOW → DENY** | ADMIN mất quyền approve suy ra |
| `ROLE_MANAGER` | ALLOW → ALLOW | **ALLOW → DENY** | Mục tiêu thay đổi |
| `ROLE_ANALYST` | ALLOW → ALLOW | DENY → DENY | Không thay đổi |
| `ROLE_VIEWER` | DENY → DENY | DENY → DENY | Không mở thêm |
| `ROLE_MANAGER` + `report:approve` | ALLOW → ALLOW | **ALLOW → ALLOW** | Permission trực tiếp vẫn có |
| `report:approve` | DENY → DENY | **ALLOW → ALLOW** | Direct permission không phụ thuộc cạnh |
| `ROLE_SUPPORT` | DENY → DENY | DENY → DENY | Không liên quan |

Phải test cả **người ở phía trên cạnh bị xóa** (ADMIN), không chỉ role tại cạnh (MANAGER). Đó là bản chất closure bắc cầu: xóa một cạnh có thể thu hồi quyền của nhiều role nguồn.

### 10.3. Đừng tự thêm cạnh ADMIN > report:approve khi chưa được phép

Nếu nghiệp vụ muốn ADMIN vẫn duyệt được sau khi MANAGER mất quyền, phải có **quyết định phân quyền riêng**:

```text
ROLE_ADMIN > report:approve
```

thêm vào H1, hoặc cấp permission trực tiếp cho những admin được phép. Đây là một lựa chọn business/policy, không phải “sửa bug test” mặc định. Tương tự, một permission duyệt có thể cần hai người độc lập hoặc SoD, không nên tự suy cho mọi admin.

## 11. Viết regression test cho thay đổi hierarchy

### 11.1. Test H0 và H1 trong cùng unit test

Mẫu JUnit 5:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

class RoleHierarchyChangeTest {

    private final RoleHierarchy before = RoleHierarchyImpl.fromHierarchy("""
            ROLE_ADMIN > ROLE_MANAGER
            ROLE_MANAGER > ROLE_ANALYST
            ROLE_ANALYST > ROLE_VIEWER
            ROLE_MANAGER > report:approve
            ROLE_ANALYST > report:read
            """);

    private final RoleHierarchy after = RoleHierarchyImpl.fromHierarchy("""
            ROLE_ADMIN > ROLE_MANAGER
            ROLE_MANAGER > ROLE_ANALYST
            ROLE_ANALYST > ROLE_VIEWER
            ROLE_ANALYST > report:read
            """);

    private boolean reaches(
            RoleHierarchy graph, String wanted, String... direct) {
        var source = java.util.Arrays.stream(direct)
                .map(SimpleGrantedAuthority::new).toList();

        return graph.getReachableGrantedAuthorities(source).stream()
                .anyMatch(a -> wanted.equals(a.getAuthority()));
    }

    @Test
    void managerLosesInheritedApproveButKeepsRead() {
        assertThat(reaches(before, "report:approve", "ROLE_MANAGER"))
                .isTrue();
        assertThat(reaches(after, "report:approve", "ROLE_MANAGER"))
                .isFalse();

        assertThat(reaches(before, "report:read", "ROLE_MANAGER"))
                .isTrue();
        assertThat(reaches(after, "report:read", "ROLE_MANAGER"))
                .isTrue();
    }

    @Test
    void adminAlsoLosesApproveTransitively() {
        assertThat(reaches(before, "report:approve", "ROLE_ADMIN"))
                .isTrue();
        assertThat(reaches(after, "report:approve", "ROLE_ADMIN"))
                .isFalse();
    }

    @Test
    void directApproveIsNotRevokedByRemovingHierarchyEdge() {
        assertThat(reaches(after, "report:approve",
                "ROLE_MANAGER", "report:approve")).isTrue();
        assertThat(reaches(after, "report:approve",
                "report:approve")).isTrue();
    }

    @Test
    void viewerNeverGainsAdmin() {
        assertThat(reaches(before, "ROLE_ADMIN", "ROLE_VIEWER"))
                .isFalse();
        assertThat(reaches(after, "ROLE_ADMIN", "ROLE_VIEWER"))
                .isFalse();
    }
}
```

**Quan trọng:** class test này chủ động tạo H0/H1 **riêng trong test** để tính delta. Nó không xác minh hệ thống deployment đã nạp H1. Cần thêm integration test với application context và cấu hình mới thật.

### 11.2. Mutation test kiểu thay đổi một cạnh

Các mutation đáng chạy hoặc review:

1. Xóa `ROLE_MANAGER > report:approve`.
2. Đảo chiều `ROLE_MANAGER > ROLE_ANALYST` thành `ROLE_ANALYST > ROLE_MANAGER`.
3. Thêm `ROLE_VIEWER > report:approve`.
4. Bỏ `ROLE_ANALYST > report:read`.
5. Đổi typo `ROLE_ANALYST` thành `ROLE_ANALYTICS`.
6. Đổi `report:approve` thành `REPORT:APPROVE`.
7. Thêm quan hệ vô tình mở đường vòng tới permission cũ.
8. Tạo cycle, ví dụ `ROLE_VIEWER > ROLE_ADMIN` khi ADMIN đã suy ra VIEWER.

**Không phải tất cả mutation đều là cấu hình hợp lệ.** `RoleHierarchyImpl` hiện đại phát hiện cycle khi xây graph và có thể ném exception; test nên bảo đảm application startup từ chối hierarchy không hợp lệ. Không dựa vào việc “framework sẽ tự tìm đường an toàn” khi graph có vòng lặp.

### 11.3. Positive delta, negative delta và invariant

Khi review thay đổi hierarchy, định nghĩa:

- **Positive delta:** quyền nào được cấp mới có chủ đích?
- **Negative delta:** quyền nào bị thu hồi có chủ đích?
- **Invariant:** quyền nào phải không đổi, gồm cả quyền trực tiếp?
- **Forbidden invariant:** quyền nào tuyệt đối không được xuất hiện cho role thấp?
- **Side effect:** thay đổi có mở/khóa thêm role nguồn khác do transitivity không?

Đối với mỗi role hoặc nhóm authority quan trọng, test một phần ở layer graph và một phần ở endpoint/method thật.

## 12. Cấu hình hierarchy mới có tự áp dụng ngay cho user đang đăng nhập?

### 12.1. Thay file YAML/text không đồng nghĩa thay bean đang chạy

`RoleHierarchyImpl.fromHierarchy(...)` tạo một đối tượng từ định nghĩa tại thời điểm khởi tạo. Các authorization managers/expression handlers có thể giữ **tham chiếu tới instance** đó. Nếu bạn sửa text hierarchy trên disk trong khi ứng dụng đang chạy, không có cơ chế mặc định bảo đảm mọi bean tự reload hoặc cập nhật closure.

**Chiến lược triển khai dễ dự đoán nhất:** thay cấu hình, chạy test, triển khai lại/restart instance và xác nhận các authorization consumers đều dùng H1. Nếu hệ thống thật sự cần cập nhật động, phải thiết kế cơ chế reload **có kiểm soát và atomic**: validate graph mới, cập nhật các consumers, làm mới caches liên quan, log version policy và tránh giai đoạn các node dùng hierarchy khác nhau.

Không dùng `setHierarchy(...)` đã deprecated làm “hot reload” ở runtime đa luồng mà chưa phân tích synchronization/references/consistency.

### 12.2. Thay hierarchy khác với thu hồi direct role

Giả sử Alice vẫn có direct `ROLE_MANAGER` từ session/JWT:

- Với **H0** đang dùng: Alice suy ra `report:approve`.
- Với **H1** đã thực sự được dùng ở điểm authorization: Alice không còn suy ra `report:approve`.
- Nếu Alice còn direct `report:approve` trong Authentication: Alice **vẫn có quyền approve** theo rule permission, dù đã xóa cạnh H0.
- Nếu session/JWT còn chứa roles/permissions cũ, cần chính sách token/session revocation riêng.

Test phải đặt rõ câu hỏi “thay hierarchy” hay “thay authorities của user”. Hai thay đổi có thể tạo kết quả giống nhau ở một endpoint nhưng tác động khác.

### 12.3. JWT và session làm xuất hiện stale authorities

Một JWT được ký sẵn có thể chứa scopes/roles tại lúc cấp token. Đến lúc người dùng bị thu hồi quyền trong database, token chưa hết hạn vẫn có thể xác thực với **claims cũ** nếu hệ thống không có revocation/introspection/cơ chế làm mới đủ chặt. Tương tự, session authentication có thể giữ authorities cũ.

Role hierarchy mới không tự làm claim trong token thay đổi. Nếu H1 xóa cạnh, việc tính quyền suy ra từ direct roles tại authorization có thể thay đổi; nhưng quyền đã có **trực tiếp** trong token vẫn có thể còn nguyên. Với hành động nhạy cảm, test thu hồi cả ở tầng hierarchy và nguồn xác thực đang có hiệu lực.

### 12.4. Multi-instance/microservice consistency

Nếu service A triển khai H1, service B còn H0, cùng role MANAGER có thể được duyệt ở B nhưng bị từ chối ở A. Nên:

- Gắn version cho policy/hierarchy đã triển khai.
- Triển khai có kiểm soát các node cùng một thay đổi chính sách.
- Kiểm tra authorization ngay ở service đang sở hữu dữ liệu/side effect.
- Có regression tests và monitoring/audit quyền nhạy cảm trong thời gian rollout.
- Không dùng role hierarchy phía frontend như nguồn sự thật.

## 13. Spring Security 6.5 và 7.x: chọn đúng API kiểm thử

### 13.1. API tính closure ổn định

Ở các dòng 6.5 và 7.x, `RoleHierarchyImpl.fromHierarchy(...)` và `RoleHierarchy.getReachableGrantedAuthorities(...)` là trọng tâm unit test. `withDefaultRolePrefix()`/`withRolePrefix()` được giới thiệu từ 6.3; `setHierarchy(...)` và constructor rỗng đã deprecated ở 6.5.

Đừng suy tên API từ Spring Boot version mà chưa kiểm tra dependency tree; Boot quản lý phiên bản Spring Security bằng BOM/parent. Khi dùng hai module với dependency khác nhau, compile và test từng module trên đúng version.

### 13.2. HTTP authorization manager ở 6.5

Trong 6.5, `AuthorityAuthorizationManager` cho phép:

```java
var manager = AuthorityAuthorizationManager
        .<RequestAuthorizationContext>hasAuthority("report:read");
manager.setRoleHierarchy(roleHierarchy);
```

Mẫu này giúp một test chứng minh **manager** thực sự được cấu hình graph, không chỉ bean graph tồn tại ở Spring context. Nếu dùng `authorizeHttpRequests(...).hasAuthority(...)` trực tiếp, xem tài liệu version để biết cơ chế nào cung cấp hierarchy cho manager do DSL tạo.

### 13.3. Spring Security 7 có AuthorizationManagerFactory

Spring Security 7.0 giới thiệu `AuthorizationManagerFactory<T>` và `DefaultAuthorizationManagerFactory<T>`, cho phép tùy chỉnh `RoleHierarchy` và `rolePrefix` cho managers được tạo qua factory. Một sketch:

```java
DefaultAuthorizationManagerFactory<RequestAuthorizationContext> factory =
        new DefaultAuthorizationManagerFactory<>();
factory.setRoleHierarchy(roleHierarchy);

AuthorizationManager<RequestAuthorizationContext> reader =
        factory.hasAuthority("report:read");
```

Đây là **fragment dành cho Spring Security 7.x**; cần imports đúng và `roleHierarchy` instance đã có. Việc factory sử dụng hierarchy phải được test ở những điểm đang dùng factory. Với custom `AuthorizationManager` tự viết, không mặc định nó đọc bean factory hoặc tự mở rộng authorities.

### 13.4. Method-security expression handler là một wiring riêng

Với `@PreAuthorize` dùng expressions, cấu hình `DefaultMethodSecurityExpressionHandler#setRoleHierarchy` là cách được tài liệu Spring Security mô tả. Các cơ chế method khác như `@Secured` hay JSR-250 có authorization managers riêng, nên cần kiểm tra version và cấu hình tương ứng. **Đừng kết luận có bean RoleHierarchy là mọi custom authorization code sẽ tự hiểu graph.**

### 13.5. Đừng nhầm AuthorizationResult với reachable authorities

`AuthorizationResult`/`AuthorizationDecision` biểu diễn kết quả allow/deny của một kiểm tra. `getReachableGrantedAuthorities` tạo **tập quyền hiệu lực**. Hai thứ thuộc các tầng khác nhau:

```text
Direct authorities
        │
        ▼
RoleHierarchy computes reachable authorities
        │
        ▼
AuthorizationManager checks required authority
        │
        ▼
AuthorizationResult / decision: granted or denied
```

Một test chỉ assert `AuthorizationDecision(true)` không biết nó đến từ direct authority hay hierarchy, trừ khi fixture và graph được thiết kế để phân biệt.

## 14. Vai trò của quyền theo đối tượng và separation of duties

### 14.1. Role hierarchy không cấp quyền mọi resource

Với `ROLE_MANAGER > report:approve`, manager có thể đủ **permission chức năng**. Nhưng việc duyệt report còn có thể yêu cầu:

```text
ALLOW_APPROVE =
    authenticated
    AND effectiveAuthorities contains "report:approve"
    AND report.tenantId = principal.tenantId
    AND report.status = WAITING_FOR_APPROVAL
    AND report.creatorId != principal.userId
```

Đây là pseudocode policy nghiệp vụ, không phải Java/Spring method có sẵn. Đặc biệt điều kiện “không tự duyệt báo cáo của mình” là **separation of duties** và không được suy ra từ role hierarchy.

### 14.2. Test role hierarchy pass không đồng nghĩa approve thành công

Một test `ROLE_MANAGER` có `report:approve` suy ra chỉ nên chứng minh functional permission. Integration test approve phải còn kiểm:

- Report thuộc cùng tenant hoặc có quyền cross-tenant được quy định.
- Report ở trạng thái được duyệt.
- User không phải tác giả nếu quy tắc cấm self-approval.
- Role bị thu hồi trước lúc lưu có được xử lý theo chính sách không.
- Audit log ghi ai duyệt và dựa trên policy version nào.

Khi hierarchy thay đổi, kiểm thử endpoint phải kiểm **không có side effect** nếu bị từ chối, ví dụ số bản ghi cập nhật bằng 0 và không phát hành sự kiện duyệt.

### 14.3. Không mở role thấp chỉ để test bớt phức tạp

Một số dự án tạo role hierarchy rất rộng:

```text
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_USER
ROLE_USER > report:read
ROLE_USER > report:approve
```

Điều này khiến mọi USER có cả quyền duyệt, dù nhiều màn hình chỉ cần quyền đọc. Hãy để quyền nhạy cảm ở cạnh/permission có business approval rõ, không dùng hierarchy thay thế một mô hình permission được thiết kế bài bản.

## 15. Ví dụ Java 17 độc lập: kiểm chứng closure và policy delta

Để hiểu cơ chế không phụ thuộc Spring, chương trình dưới dùng Java 17 thuần để mô phỏng graph authority. Nó:

- Nhận `Map<String, Set<String>>` mô tả các cạnh `source -> included authorities`.
- Duyệt đồ thị và thu thập **direct + reachable authorities**, kể cả qua nhiều bước.
- Đánh giá quyền đọc và duyệt **trước/sau thay đổi**.
- Chứng minh **direct `report:approve` không bị mất** khi xóa cạnh suy ra.
- Trình bày kết quả dạng chuỗi rõ ràng; không định nghĩa bất kỳ Spring class nào giả.

**Đây là demo khái niệm**, không thay thế `RoleHierarchyImpl` (Spring còn có validate graph, role prefix, authorization components). Không đưa implementation mini này vào production.

Tạo file `HierarchyRegressionDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class HierarchyRegressionDemo {

    static Set<String> reachable(
            Map<String, Set<String>> graph,
            Set<String> direct) {

        Set<String> result = new HashSet<>(direct);
        ArrayDeque<String> queue = new ArrayDeque<>(direct);

        while (!queue.isEmpty()) {
            String current = queue.removeFirst();
            for (String next : graph.getOrDefault(current, Set.of())) {
                if (result.add(next)) {
                    queue.addLast(next);
                }
            }
        }
        return result;
    }

    static String status(
            Map<String, Set<String>> graph,
            Set<String> direct,
            String required) {
        return reachable(graph, direct).contains(required)
                ? "ALLOW" : "DENY";
    }

    static void show(
            String label,
            Map<String, Set<String>> graph,
            Set<String> direct) {

        System.out.println(label + "-read="
                + status(graph, direct, "report:read"));
        System.out.println(label + "-approve="
                + status(graph, direct, "report:approve"));
    }

    public static void main(String[] args) {
        Map<String, Set<String>> before = Map.of(
                "ROLE_ADMIN", Set.of("ROLE_MANAGER"),
                "ROLE_MANAGER",
                    Set.of("ROLE_ANALYST", "report:approve"),
                "ROLE_ANALYST",
                    Set.of("ROLE_VIEWER", "report:read"));

        Map<String, Set<String>> after = Map.of(
                "ROLE_ADMIN", Set.of("ROLE_MANAGER"),
                "ROLE_MANAGER", Set.of("ROLE_ANALYST"),
                "ROLE_ANALYST",
                    Set.of("ROLE_VIEWER", "report:read"));

        Set<String> manager = Set.of("ROLE_MANAGER");
        Set<String> admin = Set.of("ROLE_ADMIN");
        Set<String> viewer = Set.of("ROLE_VIEWER");
        Set<String> managerWithDirectApprove =
                Set.of("ROLE_MANAGER", "report:approve");

        show("before-manager", before, manager);
        show("after-manager", after, manager);
        show("before-admin", before, admin);
        show("after-admin", after, admin);
        show("after-viewer", after, viewer);
        show("after-manager-direct", after, managerWithDirectApprove);

        System.out.println("manager-direct=" + manager);
        System.out.println("manager-reachable-after="
                + new TreeSet<>(reachable(after, manager)));
        System.out.println("viewer-is-admin="
                + reachable(after, viewer).contains("ROLE_ADMIN"));
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac HierarchyRegressionDemo.java
java HierarchyRegressionDemo
```

**Stdout dự kiến**, do các dòng `Set.of("ROLE_MANAGER")` chỉ có một phần tử và `TreeSet` sắp xếp phần hiển thị cuối:

```text
before-manager-read=ALLOW
before-manager-approve=ALLOW
after-manager-read=ALLOW
after-manager-approve=DENY
before-admin-read=ALLOW
before-admin-approve=ALLOW
after-admin-read=ALLOW
after-admin-approve=DENY
after-viewer-read=DENY
after-viewer-approve=DENY
after-manager-direct-read=ALLOW
after-manager-direct-approve=ALLOW
manager-direct=[ROLE_MANAGER]
manager-reachable-after=[ROLE_ANALYST, ROLE_MANAGER, ROLE_VIEWER, report:read]
viewer-is-admin=false
```

### 15.1. Tại sao đây là regression test hữu ích?

- Trong `before`, MANAGER có `report:approve` **chỉ nhờ cạnh hierarchy**.
- Trong `after`, bỏ cạnh manager→approve làm MANAGER và ADMIN không còn approve, nhưng quyền đọc vẫn tồn tại.
- Một principal được cấp trực tiếp `report:approve` vẫn có quyền dù cạnh bị xóa.
- Viewer không tự suy ra admin; chiều mũi tên được giữ đúng.
- `Set<String> direct` không bị tự đổi thành expanded set; đây là hai khái niệm cần giữ riêng trong mọi tầng.

### 15.2. Vì sao demo không tự coi mọi chu trình là hợp lệ?

Vòng lặp trong code dùng `result.add(next)` để tránh lặp vô hạn nếu graph có cycle, nhưng **điều này chỉ bảo đảm thuật toán demo kết thúc**, không biến graph cấp quyền vòng tròn thành chính sách hợp lệ. `RoleHierarchyImpl` thực tế có cơ chế phát hiện cycle; ứng dụng nên từ chối cấu hình không hợp lệ khi khởi tạo.

### 15.3. Giới hạn bảo mật của demo

Đây là hàm graph closure thuần Java, không có Spring `Authentication`, Servlet, JWT, session, role prefix, CSRF, method interceptors hay kiểm tra đối tượng. Trong dự án thật phải test chính **RoleHierarchyImpl** và authorization managers như các phần trước, không dùng bản mô phỏng này làm source of truth cho production.

## 16. Lỗi thường gặp khi test role hierarchy

| Hiện tượng | Nguyên nhân khả dĩ | Cách khắc phục |
| --- | --- | --- |
| Unit test closure pass, API trả 403 | HTTP manager không dùng RoleHierarchy hoặc matcher khác được chọn | Kiểm tra `setRoleHierarchy`/factory/chain và rule thực |
| HTTP GET pass nhưng `@PreAuthorize` fail | MethodSecurityExpressionHandler chưa được gắn H | Đăng ký handler đúng version và test qua Spring proxy |
| Test @WithMockUser MANAGER thấy chỉ ROLE_MANAGER | Đây là direct authorities, không phải closure | Test `getReachable...` hoặc authorization decision |
| Test suy ra luôn pass dù hierarchy bị bỏ | Fixture tự cấp hết permission | Chỉ cấp direct role trong test kế thừa |
| Xóa cạnh manager→approve mà admin vẫn approve | Có cạnh khác, direct permission hoặc consumer còn H0 | Tìm đường reachable khác, raw auth và policy version |
| Xóa cạnh nhưng client vẫn approve | Session/JWT có direct permission cũ, node còn H0 | Kiểm tra token/session, reload/restart, rollout |
| Test chỉ nhìn 200 mà không test DENY | Có thể role thấp đã bị mở | Thêm negative matrix và no-side-effect assertions |
| Đảo chiều > làm quyền tăng bất thường | Hiểu sai dấu > | Vẽ graph trước khi viết config |
| `hasRole("ROLE_MANAGER")` sai | hasRole mặc định tự thêm ROLE_ | Dùng `hasRole("MANAGER")` hoặc hasAuthority tên đầy đủ |
| `hasAuthority("report:read")` không đạt | Sai chữ hoa/prefix/claim mapping | So khớp chuỗi authority thật, test converter |
| Một @Bean RoleHierarchy tồn tại nhưng custom manager không mở rộng | Custom manager tự duyệt getAuthorities | Cấu hình manager/factory có hierarchy hoặc dùng policy khác |
| Test @WebMvcTest khác production | Slice thiếu config/các bean security | Import config đúng hoặc dùng @SpringBootTest |
| Method security không chặn self-invocation | Gọi nội bộ bỏ proxy | Test từ bean khác qua proxy |
| Cạnh thay đổi nhưng runtime không đổi | Không reload bean/manager/caches | Controlled restart hoặc atomic policy swap |
| Có cycle trong graph | Cạnh tạo vòng role | Bắt lỗi startup, yêu cầu review graph |
| Admin ở tenant A thao tác tenant B | Role hierarchy không kiểm tra object scope | Domain authorization và test multi-tenant |
| Security test 403 vì CSRF | POST không có token khi CSRF bật | Dùng `with(csrf())` trong test permission |

### 16.1. Quy trình chẩn đoán năm bước

1. **Xem direct authorities thực tế** từ test principal hoặc authentication converter (không log credentials/token).
2. **Tính closure** bằng đúng `RoleHierarchy` instance đang dùng.
3. **Xác định điểm kiểm tra quyền**: HTTP matcher/manager, method handler hay custom service.
4. **Kiểm tra integration**: điểm đó có sử dụng hierarchy instance/cấu hình đúng chưa? Có chain/proxy khác không?
5. **Đối chiếu policy version và nguồn quyền còn hiệu lực**: session/JWT, cache, node cũ, cạnh khác dẫn tới permission.

Đừng sửa bằng cách cấp `ROLE_ADMIN` cho mọi user hoặc chuyển `anyRequest().permitAll()` khi chưa biết nguyên nhân.

## 17. Checklist regression trước khi triển khai

**Thiết kế quyền:**

- [ ] Tên role/permission canonical và prefix thống nhất: `ROLE_ADMIN`, `ROLE_MANAGER`, `report:read`, `report:approve`.
- [ ] Mọi cạnh `A > B` được giải thích bằng business rule: A bao gồm B, không suy ngược.
- [ ] Đồ thị không có cycle, typos hoặc đường chuyển tiếp mở quyền ngoài ý định.
- [ ] Có bảng role→permission, phân biệt cấp trực tiếp và suy ra.
- [ ] Quyền theo đối tượng (tenant/owner/state/SoD) được kiểm soát riêng.

**Unit tests:**

- [ ] Test closure chính xác của ADMIN/MANAGER/ANALYST/VIEWER.
- [ ] Test một role không liên quan, một permission cấp trực tiếp và nhiều direct authorities.
- [ ] Test transitivity: ADMIN suy ra VIEWER và report:read.
- [ ] Test negative: VIEWER không thành ADMIN, ANALYST không approve.
- [ ] Test **H0→H1**: quyền mất, quyền giữ nguyên và direct approve tiếp tục hoạt động.

**Integration tests:**

- [ ] HTTP authorization manager/factory thực sự dùng RoleHierarchy.
- [ ] MethodSecurityExpressionHandler thực sự dùng RoleHierarchy.
- [ ] @WithMockUser chỉ cấp direct role khi muốn chứng minh kế thừa.
- [ ] POST/PATCH test có CSRF hợp lệ khi CSRF bật.
- [ ] SecurityFilterChain, RequestMatcher và AOP proxy được kích hoạt trong test.
- [ ] Có trường hợp 403/deny/no side effect, không chỉ happy path 200.
- [ ] JWT/session converter và raw authorities production được test với claims thực.

**Thay đổi và vận hành:**

- [ ] Có bảng policy delta cho mọi nguồn role bị ảnh hưởng (kể cả ADMIN ở trên cạnh).
- [ ] Không tự cấp lại permission nhạy cảm khi test mới fail.
- [ ] Xác định deployment/restart/reload strategy cho hierarchy và các consumers.
- [ ] Kiểm thử session/JWT cũ, caches và role revocation theo threat model.
- [ ] Kiểm thử các node/service dùng cùng policy version.
- [ ] Ghi audit thích hợp cho hành động nhạy cảm và phương án rollback.
- [ ] Rà soát các đường ngoài HTTP: scheduled jobs, event consumers và service calls.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Với `ROLE_ADMIN > ROLE_MANAGER > ROLE_ANALYST > ROLE_VIEWER`, user chỉ có `ROLE_ADMIN` có được xem như VIEWER không?

**Đáp án:** Có, ở authorization component có sử dụng hierarchy. Quyền được suy ra qua nhiều cạnh. `Authentication.getAuthorities()` vẫn có thể chỉ chứa direct `ROLE_ADMIN`.

**Câu 2.** `ROLE_VIEWER` có thể suy ra `ROLE_ADMIN` không?

**Đáp án:** Không. Mũi tên `>` có chiều từ role cao sang role được bao hàm, không có suy ngược.

**Câu 3.** `@WithMockUser(roles="MANAGER")` có tự thêm `report:approve` vào raw authorities không?

**Đáp án:** Không. Nó tạo direct role trong Authentication. Bộ authorization có RoleHierarchy mới tính permission suy ra theo graph; test không nên tự thêm permission ấy vào fixture.

**Câu 4.** Unit test `getReachableGrantedAuthorities(...)` pass, nhưng API 403. Điều đó chứng tỏ hierarchy bị lỗi không?

**Đáp án:** Chưa. Manager HTTP có thể không dùng hierarchy, route matcher/chain khác được chọn, CSRF có thể chặn trước, hoặc service/object policy từ chối. Cần test đúng điểm enforcement.

**Câu 5.** Nếu bỏ `ROLE_MANAGER > report:approve`, chỉ manager mất quyền approve hay admin cũng mất?

**Đáp án:** Nếu không còn đường khác và admin không có direct `report:approve`, **cả ADMIN và MANAGER** mất quyền approve suy ra qua cạnh đã xóa.

**Câu 6.** Sau khi bỏ cạnh, Alice có direct authorities `ROLE_MANAGER` và `report:approve`. Alice còn approve được không?

**Đáp án:** Còn theo rule `hasAuthority("report:approve")` vì permission trực tiếp vẫn tồn tại, miễn các điều kiện khác được đáp ứng. Muốn thu hồi direct permission phải xử lý ở nguồn cấp quyền.

**Câu 7.** Có thể kết luận `ROLE_MANAGER` có quyền report:read chỉ từ `Authentication.getAuthorities()` không?

**Đáp án:** Không nếu Authentication chỉ chứa role trực tiếp. Phải tính closure bằng H hoặc đánh giá qua authorization component đã tích hợp H.

**Câu 8.** Vì sao không dùng `@WithMockUser(authorities={"ROLE_MANAGER","report:read"})` để chứng minh hierarchy suy ra quyền đọc?

**Đáp án:** Vì permission đã được cấp trực tiếp, test vẫn pass ngay cả khi hierarchy không hoạt động. Chỉ cấp `ROLE_MANAGER` trong fixture của test suy ra.

**Câu 9.** Khi sửa hierarchy text trên disk, có chắc mọi server node áp dụng tức thời không?

**Đáp án:** Không. Bean/managers có thể đang giữ graph cũ. Cần deployment/restart hoặc reload được thiết kế đồng bộ, có validation và test.

**Câu 10.** Một user có report:approve suy ra có tự duyệt được báo cáo của tenant khác không?

**Đáp án:** Không. Hierarchy chỉ giải quyết quyền chức năng; domain policy còn phải kiểm tra tenant, owner, report status và ràng buộc nghiệp vụ.

**Câu 11.** Tại sao test quyền suy ra phải có ca **không được phép**?

**Đáp án:** Một cạnh sai hoặc đảo chiều có thể mở quyền cho role thấp. Chỉ kiểm quyền của admin sẽ không phát hiện leo thang quyền đó.

**Câu 12.** Trong Spring Security 7, có API nào hỗ trợ đưa RoleHierarchy vào managers được tạo tập trung?

**Đáp án:** `DefaultAuthorizationManagerFactory` có `setRoleHierarchy(...)`. Cần bảo đảm code thực dùng factory tương ứng; custom manager không tự hưởng cấu hình nếu chưa tích hợp.

**Kết luận:** Để kiểm thử role hierarchy đúng, phải xác định **đầu vào trực tiếp**, **đồ thị quyền**, **tập quyền có thể đạt tới**, và **điểm authorization thật sự dùng tập ấy**. Khi thay đổi graph, viết regression tests cho **quyền mới, quyền bị thu hồi, quyền giữ nguyên và quyền tuyệt đối không được cấp**. Bảo đảm cấu hình HTTP/method sử dụng cùng hierarchy, tránh stale token/instance, và giữ kiểm tra tenant/owner ở service.

## Tài liệu tham khảo chính thức

- Spring Security — Authorization Architecture, Hierarchical Roles: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security 6.5 — Authorization Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html
- Spring Security — Method Security, RoleHierarchy và expression handler: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security 6.5 — Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — RoleHierarchyImpl Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/hierarchicalroles/RoleHierarchyImpl.html
- Spring Security 7.0 — RoleHierarchyImpl API: https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/access/hierarchicalroles/RoleHierarchyImpl.html
- Spring Security 6.5 — AuthorityAuthorizationManager, setRoleHierarchy: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorityAuthorizationManager.html
- Spring Security 7.0 — DefaultAuthorizationManagerFactory: https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/authorization/DefaultAuthorizationManagerFactory.html
- Spring Security — MockMvc integration tests: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security — @WithMockUser test annotation: https://docs.spring.io/spring-security/reference/servlet/test/method.html

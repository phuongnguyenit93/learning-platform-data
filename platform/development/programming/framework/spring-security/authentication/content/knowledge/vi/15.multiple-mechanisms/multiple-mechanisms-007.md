# Quyền nạp từ các nguồn khác nhau và yêu cầu chuẩn hóa trong Spring Security

## 1. Vấn đề khi ứng dụng có nhiều cơ chế xác thực

Một hệ thống có thể cho phép cùng lúc nhiều đường đăng nhập và nhiều nguồn quản lý quyền:

- Nhân viên đăng nhập bằng **username/password** nội bộ, các vai trò được đọc từ cơ sở dữ liệu.
- Nhân viên đăng nhập **OpenID Connect (OIDC)**; hệ thống nhận nhóm của họ từ nhà cung cấp danh tính (IdP).
- API nhận **OAuth2 access token dạng JWT**, trong đó có scope như `orders.read`.
- Tài khoản máy (service account) được cấp một tập quyền riêng.
- Hệ thống cũ có thể dùng LDAP groups hoặc một `AuthenticationProvider` tùy chỉnh.

Các nguồn có **tên gọi, đơn vị tin cậy, thời điểm cập nhật và ý nghĩa quyền khác nhau**. Nếu ứng dụng dùng nguyên xi mọi giá trị để phân quyền, chính sách trở nên khó kiểm soát:

~~~text
Local DB      : SUPPORT, ORDER_VIEW
OIDC groups   : groups/support, groups/order-readers
JWT scopes    : orders.read, orders.write
LDAP groups   : cn=Support,ou=Groups,...
                              |
                              v
              Chính sách của ứng dụng
              ROLE_SUPPORT
              orders:read
              orders:write
~~~

Bài học này tập trung vào **chuẩn hóa quyền (authority normalization)**: chỉ chuyển các giá trị từ nguồn đã xác minh thành một tập `GrantedAuthority` **có ý nghĩa thống nhất, xác định được và kiểm soát ở phía server**.

Mục tiêu:

1. Phân biệt xác thực danh tính với phân quyền và hiểu cấu trúc `Authentication.getAuthorities()`.
2. Định nghĩa bảng ánh xạ riêng cho DB, IdP groups, JWT scopes và các nguồn được phép.
3. Hiểu `ROLE_`, `SCOPE_`, quyền nghiệp vụ và các cách `hasRole` / `hasAuthority` kiểm tra chuỗi.
4. Loại bỏ quyền trùng, quyền không được duyệt, tên không hợp lệ và trường hợp lẫn nguồn.
5. Tích hợp điểm chuẩn hóa vào `UserDetailsService`/`AuthenticationProvider`, OAuth2/OIDC login và JWT resource server đúng vị trí.
6. Xử lý danh tính, tenant, nguồn tin cậy, phân quyền hết hạn và bài toán “deny” trước khi tổng hợp quyền.
7. Kiểm thử kết quả chuẩn hóa một cách xác định, tránh vô tình cấp `ROLE_ADMIN` cho dữ liệu do client kiểm soát.

Ví dụ dùng **Java 17+, Spring Security 6.x**. Đoạn chương trình chạy độc lập bằng Maven để tập trung vào quy tắc ánh xạ; các ví dụ tích hợp OAuth2/JWT là đoạn cấu hình cần đặt trong ứng dụng Servlet thật.

## 2. Authorities là gì và được dùng ở đâu?

Spring Security lưu danh sách `GrantedAuthority` trong đối tượng `Authentication` sau khi danh tính được xác minh. `GrantedAuthority` có hợp đồng đơn giản:

~~~java
public interface GrantedAuthority {
    String getAuthority();
}
~~~

`SimpleGrantedAuthority` biểu diễn một quyền bằng chuỗi. Ví dụ:

~~~java
new SimpleGrantedAuthority("ROLE_SUPPORT");
new SimpleGrantedAuthority("orders:read");
new SimpleGrantedAuthority("SCOPE_orders.read");
~~~

Các giá trị trên là **ba chuỗi khác nhau**, không tự động tương đương.

| Chuỗi authority | Ý nghĩa theo một chính sách mẫu | Cách kiểm tra |
| --- | --- | --- |
| `ROLE_SUPPORT` | Vai trò hỗ trợ | `hasRole("SUPPORT")` hoặc `hasAuthority("ROLE_SUPPORT")` |
| `orders:read` | Quyền nghiệp vụ đọc đơn hàng | `hasAuthority("orders:read")` |
| `orders:write` | Quyền nghiệp vụ sửa đơn hàng | `hasAuthority("orders:write")` |
| `SCOPE_orders.read` | Scope OAuth2/JWT theo quy ước mặc định | `hasAuthority("SCOPE_orders.read")` |
| `OIDC_USER` | Authority đặc biệt của một số luồng OIDC login | Không coi là vai trò nghiệp vụ hay admin |

Với mặc định thông thường, biểu thức `hasRole("SUPPORT")` tìm chuỗi `ROLE_SUPPORT` (prefix `ROLE_`). `hasAuthority("ROLE_SUPPORT")` so khớp chính xác. Nếu ứng dụng thay đổi default role prefix, kết quả có thể khác; hãy tài liệu hóa chính sách prefix của dự án.

**Không tồn tại cơ chế tự động** hiểu rằng `SUPPORT` ở DB, `groups/support` ở IdP và `SCOPE_support` từ JWT là cùng một vai trò. Nhà phát triển phải thiết lập quy tắc đó một cách tường minh.

### Phân biệt 4 khái niệm

- **Authentication**: ai đang truy cập, đã xác thực chưa, đến từ cơ chế nào.
- **Role**: nhóm trách nhiệm, ví dụ `ROLE_SUPPORT` hoặc `ROLE_OPERATOR`.
- **Permission/authority**: hành động cụ thể, ví dụ `orders:read`, `orders:write`. Role cũng được biểu diễn bằng authority trong Spring Security.
- **Scope**: quyền được cấp cho một OAuth2 client/access token theo giao thức của authorization server. Scope không mặc nhiên là role của người dùng.

Ví dụ một token có scope `orders.read` chỉ chứng minh authorization server đã cấp scope cho token **trong ngữ cảnh issuer, audience, subject/client và chính sách của nó**. Nó không tự chứng minh chủ token là quản trị viên hệ thống.

## 3. Xây dựng “từ điển quyền chuẩn” của ứng dụng

Trước khi viết converter, hãy quyết định tập authority đích. Ví dụ:

| Authority chuẩn | Ý nghĩa | Có thể đến từ đâu |
| --- | --- | --- |
| `ROLE_SUPPORT` | Vai trò nhân viên hỗ trợ | DB role nội bộ; nhóm hỗ trợ của IdP đã xác minh |
| `ROLE_OPERATOR` | Vai trò vận hành | DB role nội bộ; nhóm vận hành IdP đã kiểm chứng |
| `orders:read` | Xem đơn hàng phù hợp với tenant và ownership | DB permission; nhóm đọc đơn của IdP; JWT scope được phép |
| `orders:write` | Chỉnh sửa đơn hàng phù hợp với tenant và ownership | DB permission; JWT scope đã được cấp đúng policy |
| `ROLE_ADMIN` | Vai trò quản trị đặc biệt | Chỉ nguồn quản trị được phê duyệt riêng; không tự suy ra từ text chứa chữ “admin” |

Một **bảng ánh xạ có kiểm soát** có thể là:

| Nguồn đã xác minh | Giá trị ở nguồn | Authority chuẩn |
| --- | --- | --- |
| Local DB | `role:support` | `ROLE_SUPPORT` |
| Local DB | `role:operator` | `ROLE_OPERATOR` |
| Local DB | `perm:orders-view` | `orders:read` |
| Local DB | `perm:orders-edit` | `orders:write` |
| OIDC IdP group | `groups/support` | `ROLE_SUPPORT` |
| OIDC IdP group | `groups/operators` | `ROLE_OPERATOR` |
| OIDC IdP group | `groups/order-readers` | `orders:read` |
| Verified JWT scope | `orders.read` | `orders:read` |
| Verified JWT scope | `orders.write` | `orders:write` |

Các giá trị khác, ví dụ `groups/admin`, `admin`, `ROLE_ADMIN` hoặc `orders.read.all-tenants`, **không được cấp** nếu chưa có mục ánh xạ minh thị. Đây là nguyên tắc **default deny** cho các quyền chưa được phê duyệt.

Đừng dùng quy tắc rộng như:

~~~java
// KHÔNG AN TOÀN: client/IdP có thể đưa mọi chuỗi vào kết quả.
String role = "ROLE_" + externalValue.toUpperCase();

// KHÔNG AN TOÀN: mọi group bắt đầu bằng "admin" biến thành admin.
if (group.toLowerCase().contains("admin")) {
    return "ROLE_ADMIN";
}
~~~

Thay vào đó, ánh xạ **giá trị cụ thể**, có kiểm tra nguồn và thay đổi qua quy trình xét duyệt.

## 4. Nguồn tin cậy phải được xác minh trước bước chuẩn hóa

Một bản ghi `RawGrant(source, value)` chỉ đáng tin nếu **adapter nội bộ** đã xác minh nó thực sự đến từ nguồn đó. Không cho client gửi JSON như `{"source":"LOCAL_DB","role":"admin"}` rồi tự biến nó thành authority.

| Nguồn | Điều kiện trước khi đọc role/group/scope |
| --- | --- |
| Local DB | User đã được xác thực; bản ghi quyền đọc bằng truy vấn có kiểm soát, đúng subject và tenant, tài khoản đang hoạt động |
| OIDC group | Identity token/UserInfo từ IdP tin cậy, flow đã xác minh issuer, signature/nonce/audience khi áp dụng, claim nhóm có semantics đã ký kết |
| JWT access token | JWT được `JwtDecoder` xác minh chữ ký, hạn dùng và issuer; audience/token type/tenant được validate theo cấu hình; claim scope đúng ngữ nghĩa |
| LDAP group | Kết nối LDAPS/TLS thích hợp, principal đã xác thực, group được truy vấn từ directory đáng tin |
| API key/service account | Key đã được xác minh qua `AuthenticationProvider`; quyền nạp từ record của service account trên server |

**Issuer và audience quan trọng.** Cùng một chuỗi `groups/support` từ hai IdP có thể có nghĩa rất khác. Nếu đa issuer, không gộp thẳng vào một namespace chung; dùng khóa ánh xạ ít nhất gồm `source + issuer + raw value`, và với nhiều tenant có thể thêm tenant/organization.

**Subject cũng quan trọng.** `sub=user-123` của issuer A không tự động là cùng người với `sub=user-123` của issuer B. ID nội bộ nên được xác định từ định danh ổn định như cặp `(issuer, sub)` đã liên kết theo cơ chế được phê duyệt. Email chưa được xác minh, email đổi được hoặc chỉ trùng địa chỉ không đủ để cộng quyền.

## 5. Pipeline chuẩn hóa đáng tin cậy

~~~text
       Authentication Provider / JWT Decoder / OIDC Client
                           |
                Xác minh danh tính/token
                           |
              Kiểm tra account + tenant + issuer
                           |
      Adapter lấy grants từ nguồn đã được xác minh
                           |
             (Source, rawValue, provenance)
                           |
             AuthorityNormalizer (allowlist)
                           |
          Loại giá trị không hợp lệ/không duyệt
                           |
       Dedupe + sắp xếp + authorities chuẩn
                           |
             Authentication authenticated
                           |
              AuthorizationManager
                           |
       Kiểm tra permission VÀ quyền trên resource
~~~

Quy tắc triển khai:

1. **Dữ liệu thô bất biến và có nguồn gốc**: giữ `Source`, mã role/group gốc, định danh issuer hoặc policy version để audit, ít nhất cho đến lúc mapping xong.
2. **Một canonical vocabulary**: quyết định viết hoa/thường, prefix và tên permission. Không trộn `ORDER_READ`, `order.read`, `orders:read` trong cùng ứng dụng nếu muốn một ý nghĩa.
3. **Ánh xạ theo nguồn**: cùng một raw string có thể được chấp nhận ở DB và bị từ chối ở JWT; khác nguồn thì không chia sẻ allowlist.
4. **Không sửa chuỗi một cách mù quáng**: `trim`, lowercase hoặc chuẩn hóa Unicode chỉ khi **giao thức nguồn quy định** và có test phù hợp. Với scope và nhóm có phân biệt hoa/thường, tự động sửa có thể làm rộng quyền.
5. **Không công nhận quyền lạ**: từ chối/loại bỏ và đo lường; nếu hệ thống bắt buộc quyền đó mới được hoạt động, chặn giao dịch hoặc từ chối login theo policy.
6. **Khử trùng lặp**: một người có thể nhận `orders:read` từ DB và OIDC; kết quả không cần hai bản ghi giống nhau.
7. **Không tự ghép những identity khác nhau**: chỉ tổng hợp khi các grants thực sự thuộc **cùng subject và cùng phạm vi tenant** đã được xác minh.
8. **Trạng thái khóa/thu hồi có ưu tiên**: nếu tài khoản bị disabled/suspended, chỉ loại một authority không đủ; cần cấm authentication/authorization theo policy. `GrantedAuthority` thông thường biểu diễn các quyền được cấp, không biểu diễn “deny” có độ ưu tiên tự động.
9. **Lưu lại dấu vết nguồn riêng với danh sách cuối**: sau khi khử trùng lặp `ROLE_SUPPORT`, bản thân `SimpleGrantedAuthority` không còn cho biết nguồn cấp là DB hay IdP; audit cần giữ provenance ở lớp khác.

## 6. Ví dụ Java 17 chạy được: chuẩn hóa từ ba nguồn

Ví dụ dùng `SimpleGrantedAuthority` của **Spring Security Core**. Các `RawGrant` trong `main` là **dữ liệu minh họa đã được adapter tin cậy cung cấp**; lớp này không tự giải mã JWT hoặc truy vấn DB. Mục đích là minh họa cơ chế normalize có chính sách cụ thể, tránh cấp quyền bằng cách nối chuỗi.

### 6.1. Tạo dự án Maven

~~~text
authority-normalization-demo/
├── pom.xml
└── src/
    ├── main/java/demo/authorities/AuthorityNormalizationDemo.java
    └── test/java/demo/authorities/AuthorityNormalizationDemoTest.java
~~~

File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>authority-normalization-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-core</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.4.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Spring Boot parent quản lý phiên bản Spring Security và JUnit tương thích; chương trình không cần chạy Spring Boot web server.

### 6.2. Mã nguồn chính

File `src/main/java/demo/authorities/AuthorityNormalizationDemo.java`:

~~~java
package demo.authorities;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeSet;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class AuthorityNormalizationDemo {

    private AuthorityNormalizationDemo() {
    }

    // Enum mô tả nguồn ĐÃ ĐƯỢC XÁC MINH trước khi tới normalizer.
    public enum Source {
        LOCAL_DB, IDP_GROUP, JWT_SCOPE
    }

    public record RawGrant(Source source, String value) {
        public RawGrant {
            Objects.requireNonNull(source, "source");
            Objects.requireNonNull(value, "value");
        }
    }

    public static final class AuthorityNormalizer {

        // Bảng ánh xạ tường minh, chỉ server được quyết định.
        // Trong sản phẩm thật có thể đưa vào cấu hình có version/audit.
        private static final Map<Source, Map<String, String>> ALLOWED =
            Map.of(
                Source.LOCAL_DB,
                Map.of(
                    "role:support", "ROLE_SUPPORT",
                    "role:operator", "ROLE_OPERATOR",
                    "perm:orders-view", "orders:read",
                    "perm:orders-edit", "orders:write"
                ),
                Source.IDP_GROUP,
                Map.of(
                    "groups/support", "ROLE_SUPPORT",
                    "groups/operators", "ROLE_OPERATOR",
                    "groups/order-readers", "orders:read"
                ),
                Source.JWT_SCOPE,
                Map.of(
                    "orders.read", "orders:read",
                    "orders.write", "orders:write"
                )
            );

        public List<GrantedAuthority> normalize(
                Collection<RawGrant> trustedSourceGrants) {

            Objects.requireNonNull(
                trustedSourceGrants, "trustedSourceGrants");

            // TreeSet: dedupe và trả thứ tự ổn định cho test/log.
            TreeSet<String> canonical = new TreeSet<>();

            for (RawGrant raw : trustedSourceGrants) {
                Objects.requireNonNull(raw, "raw grant");

                // Không có logic "ROLE_" + raw.value().
                String mapped = ALLOWED.get(raw.source()).get(raw.value());
                if (mapped != null) {
                    canonical.add(mapped);
                }
                // Không có mapping -> không cấp quyền.
            }

            List<GrantedAuthority> result = new ArrayList<>();
            for (String authority : canonical) {
                result.add(new SimpleGrantedAuthority(authority));
            }

            // Không cho code sau vô ý mutate quyền đã chuẩn hóa.
            return List.copyOf(result);
        }
    }

    public static void main(String[] args) {
        AuthorityNormalizer normalizer = new AuthorityNormalizer();

        // Chỉ mang tính minh họa: giả định adapter đã xác minh cùng
        // subject + tenant và các giá trị thực sự từ đúng nguồn.
        List<RawGrant> trustedGrants = List.of(
            new RawGrant(Source.LOCAL_DB, "role:support"),
            new RawGrant(Source.IDP_GROUP, "groups/order-readers"),
            new RawGrant(Source.JWT_SCOPE, "orders.read"),
            new RawGrant(Source.JWT_SCOPE, "admin"),
            new RawGrant(Source.IDP_GROUP, "groups/admin"),
            new RawGrant(Source.LOCAL_DB, "role:support")
        );

        List<GrantedAuthority> authorities =
            normalizer.normalize(trustedGrants);

        List<String> names = authorities.stream()
            .map(GrantedAuthority::getAuthority)
            .toList();

        System.out.println("authorities=" + names);
        System.out.println("hasSupport=" + names.contains("ROLE_SUPPORT"));
        System.out.println("canReadOrders=" + names.contains("orders:read"));
        System.out.println("hasAdmin=" + names.contains("ROLE_ADMIN"));
    }
}
~~~

Chạy ở thư mục chứa `pom.xml` với JDK 17+ và Maven:

~~~bash
mvn -q -DskipTests compile
mvn -q -Dexec.mainClass=demo.authorities.AuthorityNormalizationDemo exec:java
~~~

Các dòng chương trình chủ động in ra, theo đúng thứ tự:

~~~text
authorities=[ROLE_SUPPORT, orders:read]
hasSupport=true
canReadOrders=true
hasAdmin=false
~~~

Maven có thể in thêm thông báo hệ thống tùy môi trường. Code dùng thư viện Spring Security trên classpath nên không thể chạy bằng `javac` đơn lẻ nếu không cung cấp dependency.

### 6.3. Phân tích chi tiết ví dụ

**Đầu vào có thông tin nguồn:** `RawGrant(Source.LOCAL_DB, "role:support")` khác `RawGrant(Source.JWT_SCOPE, "role:support")`. Dù chuỗi giống nhau, chỉ mapping của `LOCAL_DB` cho phép nó trở thành `ROLE_SUPPORT`.

**Không tin quyền tên “admin”:** `admin` từ JWT và `groups/admin` từ IdP không có trong allowlist, vì vậy không tạo `ROLE_ADMIN`. Đặc biệt, nếu JWT chứa `ROLE_ADMIN` trong một claim do client hoặc bên thứ ba cung cấp, việc chuyển trực tiếp sang `SimpleGrantedAuthority("ROLE_ADMIN")` có thể gây nâng quyền.

**Một permission từ nhiều nguồn:** `groups/order-readers` và `orders.read` đều chuyển thành `orders:read`. `TreeSet` loại bản ghi trùng và sắp xếp ổn định. Đây chỉ là hành vi đúng khi cả hai nguồn đã được xác minh, **cùng identity** và được policy cho phép tổng hợp.

**Bất biến của tập quyền:** `List.copyOf` trả danh sách không thể thêm/bớt phần tử bằng thao tác thường. Điều này không biến source thành đáng tin; nó chỉ giảm khả năng thành phần sau vô tình chỉnh sửa authority collection.

**Không tự xác thực người dùng:** `normalize` trả `List<GrantedAuthority>`, không trả `Authentication` đã được tin cậy. Tại code ứng dụng thật, chỉ sau khi provider/IdP/JWT decoder xác minh được danh tính và kiểm tra trạng thái tài khoản, adapter mới chuyển các nguồn quyền đến normalizer.

## 7. Kiểm thử nguồn, quyền trùng và trường hợp độc hại

Tạo `src/test/java/demo/authorities/AuthorityNormalizationDemoTest.java`:

~~~java
package demo.authorities;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;

import static demo.authorities.AuthorityNormalizationDemo.Source.*;
import static org.junit.jupiter.api.Assertions.*;

class AuthorityNormalizationDemoTest {

    private final AuthorityNormalizationDemo.AuthorityNormalizer normalizer =
        new AuthorityNormalizationDemo.AuthorityNormalizer();

    private List<String> names(
            List<AuthorityNormalizationDemo.RawGrant> raw) {
        return normalizer.normalize(raw).stream()
            .map(GrantedAuthority::getAuthority)
            .toList();
    }

    private AuthorityNormalizationDemo.RawGrant raw(
            AuthorityNormalizationDemo.Source source,
            String value) {
        return new AuthorityNormalizationDemo.RawGrant(source, value);
    }

    @Test
    void mapsTheSamePermissionFromDifferentVerifiedSourcesOnce() {
        assertEquals(List.of("ROLE_SUPPORT", "orders:read"),
            names(List.of(
                raw(LOCAL_DB, "role:support"),
                raw(IDP_GROUP, "groups/order-readers"),
                raw(JWT_SCOPE, "orders.read"),
                raw(LOCAL_DB, "role:support")
            )));
    }

    @Test
    void sameRawStringFromDifferentSourceDoesNotGainRole() {
        assertEquals(List.of("ROLE_SUPPORT"),
            names(List.of(raw(LOCAL_DB, "role:support"))));

        assertEquals(List.of(),
            names(List.of(raw(JWT_SCOPE, "role:support"))));
    }

    @Test
    void unknownAdminLookingValuesDoNotBecomeAdmin() {
        assertEquals(List.of(),
            names(List.of(
                raw(IDP_GROUP, "groups/admin"),
                raw(JWT_SCOPE, "admin"),
                raw(LOCAL_DB, "ROLE_ADMIN")
            )));
    }

    @Test
    void exactMappingDoesNotSilentlyTrimOrChangeCase() {
        assertEquals(List.of(),
            names(List.of(
                raw(JWT_SCOPE, "ORDERS.READ"),
                raw(JWT_SCOPE, " orders.read "),
                raw(IDP_GROUP, "Groups/Support")
            )));
    }

    @Test
    void distinctApprovedGrantsStayDistinct() {
        assertEquals(List.of("ROLE_OPERATOR", "orders:write"),
            names(List.of(
                raw(LOCAL_DB, "role:operator"),
                raw(JWT_SCOPE, "orders.write")
            )));
    }

    @Test
    void noGrantsMeansNoPermissions() {
        assertEquals(List.of(), names(List.of()));
    }

    @Test
    void rejectsNullInputInsteadOfGuessing() {
        assertThrows(NullPointerException.class,
            () -> normalizer.normalize(null));
        assertThrows(NullPointerException.class,
            () -> new AuthorityNormalizationDemo.RawGrant(
                null, "role:support"));
        assertThrows(NullPointerException.class,
            () -> new AuthorityNormalizationDemo.RawGrant(
                LOCAL_DB, null));
    }

    @Test
    void resultCollectionIsImmutable() {
        List<GrantedAuthority> result = normalizer.normalize(
            List.of(raw(LOCAL_DB, "role:support")));

        assertThrows(UnsupportedOperationException.class,
            () -> result.clear());
        assertEquals("ROLE_SUPPORT", result.get(0).getAuthority());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Kỳ vọng:** 8 test qua khi chạy trên JDK/Maven với phiên bản dependency tương thích trong `pom.xml`. Các kiểm thử này là mã nguồn dành cho thực hành; hãy thực thi trong dự án của mình để xác nhận. Chúng kiểm tra nhiều trường hợp **không được cấp quyền** chứ không chỉ đầu vào hợp lệ.

### Vì sao phải test âm tính?

Nếu code dùng `raw.toUpperCase()` rồi thêm prefix `ROLE_`, test “admin-looking” sẽ phát hiện có thể xuất hiện `ROLE_ADMIN`. Nếu code bỏ qua nguồn, test “same raw different source” sẽ phát hiện JWT scope mạo danh role DB. Nếu code tự `trim` hoặc lowercase, test “exact mapping” sẽ phát hiện chuẩn hóa có thể thay đổi ngữ nghĩa của quyền.

Test cũng đảm bảo việc bổ sung nguồn quyền trong tương lai không vô tình làm thay đổi người dùng hiện có. Khi cập nhật map, cần thêm test chứng minh từng mục mới là chính sách đã duyệt, và cập nhật audit/version.

## 8. Đưa danh sách authority vào Authentication đúng lúc

Luồng tích hợp với custom provider hoặc `UserDetailsService`:

~~~text
HTTP login
 -> Filter tạo token chưa xác thực
 -> AuthenticationManager chọn AuthenticationProvider
 -> Provider kiểm tra password / credential / account status
 -> Adapter đọc roles đã được xác minh của đúng user/tenant
 -> AuthorityNormalizer.normalize(...)
 -> Provider trả Authentication đã xác thực với canonical authorities
 -> SecurityContextRepository lưu context nếu dùng session
 -> AuthorizationManager kiểm tra endpoint
~~~

Ví dụ **đoạn mã minh họa trong một provider sau khi kiểm tra credential thành công**:

~~~java
// verifiedUser: đối tượng user đã xác minh, không do client tự đặt.
// rawGrants: quyền được adapter server đọc cho đúng verifiedUser.
List<GrantedAuthority> authorities = normalizer.normalize(rawGrants);

Authentication authenticated =
    UsernamePasswordAuthenticationToken.authenticated(
        verifiedUser,
        null,
        authorities
    );

return authenticated;
~~~

Đoạn này **không phải chương trình độc lập**: `verifiedUser`, `rawGrants`, `normalizer` phải đến từ provider/adapter đáng tin. Không làm:

~~~java
// SAI: chỉ đọc body/claims từ request rồi tự đánh dấu authenticated.
List<GrantedAuthority> roles = requestRoles.stream()
    .map(SimpleGrantedAuthority::new)
    .toList();

return UsernamePasswordAuthenticationToken.authenticated(
    submittedUsername, null, roles);
~~~

**Nếu dùng `DaoAuthenticationProvider` và `UserDetailsService`**, điểm nạp quyền có thể nằm trong `UserDetailsService.loadUserByUsername`: sau khi truy vấn đúng tài khoản, xây dựng `UserDetails` với canonical authorities; provider sẽ dùng `PasswordEncoder` kiểm tra password. Một số provider có `GrantedAuthoritiesMapper` riêng để xử lý tập quyền sau khi tải. Nên tái sử dụng một service normalizer và policy thống nhất để không có hai cách dịch quyền khác nhau giữa các luồng đăng nhập.

**Nếu dùng session**, danh sách quyền ở `Authentication` trong `SecurityContext` có thể là một snapshot. Thay role trong DB hoặc IdP không tự động cập nhật mọi session còn sống. Xác định rõ TTL, cơ chế refresh quyền, session invalidation khi khóa tài khoản và cách kiểm soát quyền nhạy cảm tại mỗi request.

## 9. Tích hợp OAuth2/OIDC login

Trong `oauth2Login`, Spring Security cho phép tùy biến việc ánh xạ authorities thông qua `GrantedAuthoritiesMapper` hoặc một `OAuth2UserService`/`OidcUserService` được ủy quyền. Bạn có thể dùng mapper để chuyển các `OidcUserAuthority` / `OAuth2UserAuthority` và claim phù hợp thành canonical authorities của ứng dụng.

Đoạn cấu hình khung:

~~~java
// Đặt bên trong SecurityFilterChain, khi ứng dụng có
// spring-boot-starter-oauth2-client và cấu hình IdP:
http.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(userInfo -> userInfo
        .userAuthoritiesMapper(approvedAuthoritiesMapper)
    )
);
~~~

`approvedAuthoritiesMapper` là một `GrantedAuthoritiesMapper` do ứng dụng cung cấp. Nó cần:
1. Nhận các `GrantedAuthority` từ Spring Security sau khi flow OAuth2/OIDC đã hoàn thành.
2. Chỉ lấy groups/claims đúng nghĩa từ `OidcUserAuthority`, `OAuth2UserAuthority` hoặc thông tin user đã được dịch vụ đáng tin tải về.
3. Ràng buộc issuer/client registration và tenant theo cấu hình. **Không** lấy mọi claim có tên “roles” từ mọi IdP rồi coi là role admin.
4. Dịch các raw group qua allowlist nguồn (`Source.IDP_GROUP`), khử trùng lặp, trả `Collection<? extends GrantedAuthority>`.
5. Giữ/loại các authority hệ thống được Spring Security tạo ra theo chính sách rõ ràng. Không vô ý bỏ quyền hệ thống mà chức năng khác phụ thuộc, cũng không biến `OIDC_USER` thành `ROLE_USER` hoặc `ROLE_ADMIN` mà chưa thiết kế.

Ví dụ một IdP A phát `groups/support` và IdP B phát cũng chuỗi ấy. Nếu chỉ A được phép cấp `ROLE_SUPPORT`, đích ánh xạ phải phân biệt:

~~~text
(issuer=https://idp-a.example, groups/support) -> ROLE_SUPPORT
(issuer=https://idp-b.example, groups/support) -> không cấp quyền
~~~

`GrantedAuthoritiesMapper` dùng được khi thông tin để phân biệt nguồn đã có sẵn. Nếu phải gọi một hệ thống khác để lấy quyền bổ sung và cần ngữ cảnh token/issuer, một `OAuth2UserService` hoặc `OidcUserService` tùy biến có thể phù hợp hơn. Lưu ý các lệnh gọi ngoài phải có timeout, fallback an toàn và không cho lỗi tải quyền ngẫu nhiên trở thành “full access”.

## 10. Tích hợp JWT Resource Server

Khi API là OAuth2 Resource Server, Spring Security thường tạo một `JwtAuthenticationToken` từ access token đã xác minh. Mặc định `JwtGrantedAuthoritiesConverter` có thể đọc scope/scp và sinh authority có prefix `SCOPE_`, ví dụ:

~~~text
JWT scope : orders.read
-> GrantedAuthority: SCOPE_orders.read
-> hasAuthority("SCOPE_orders.read") == true
~~~

Nếu hệ thống đã có canonical permission `orders:read`, có hai chiến lược hợp lệ:

**Chiến lược 1: Giữ namespace mặc định.** Viết rule `hasAuthority("SCOPE_orders.read")` riêng cho API JWT, trong khi role DB có rule khác. Điều này giảm chuyển đổi nhưng khó có chính sách thống nhất nếu nhiều cơ chế cùng chạm một endpoint.

**Chiến lược 2: Dịch scope đã duyệt.** Áp dụng `JwtAuthenticationConverter#setJwtGrantedAuthoritiesConverter` để biến scope hợp lệ thành canonical permissions, ví dụ `orders.read → orders:read`; nếu cần giữ `SCOPE_` mặc định, kết hợp có kiểm soát và kiểm thử chính xác tập kết quả. Không tự gắn `ROLE_` cho mọi scope vì scope do authorization server cấp không nhất thiết là vai trò của chủ tài khoản.

Ví dụ **đoạn cấu hình minh họa**, giả định `normalizer` đã được định nghĩa như mục 6 và `JwtDecoder` được cấu hình đầy đủ:

~~~java
JwtAuthenticationConverter jwtConverter =
    new JwtAuthenticationConverter();

jwtConverter.setJwtGrantedAuthoritiesConverter(jwt -> {
    // Ví dụ issuer đáng tin cung cấp claim "scp" dạng List<String>.
    List<String> scopes = jwt.getClaimAsStringList("scp");
    if (scopes == null) {
        scopes = List.of();
    }

    List<AuthorityNormalizationDemo.RawGrant> raw = scopes.stream()
        .map(s -> new AuthorityNormalizationDemo.RawGrant(
            AuthorityNormalizationDemo.Source.JWT_SCOPE, s))
        .toList();

    return normalizer.normalize(raw);
});

// Đặt trong SecurityFilterChain của Resource Server:
http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtConverter))
);
~~~

Đoạn này **không phải ứng dụng độc lập**; cần import OAuth2 Resource Server, `JwtAuthenticationConverter`, `List` và `normalizer`. Quan trọng hơn, token phải đi qua cấu hình decoder/validator bảo đảm **chữ ký, issuer, hạn dùng và audience** phù hợp chính sách. Tùy provider, scope nằm trong chuỗi `scope` phân tách bằng khoảng trắng hoặc mảng `scp`. Adapter phải hiểu đúng định dạng nguồn; đừng đoán hoặc xử lý tùy tiện hai dạng rồi cấp quyền rộng hơn.

Nếu hỗ trợ đa issuer, chọn `JwtDecoder`/authentication manager resolver phù hợp và áp dụng bảng map theo issuer thay vì dùng một policy cho mọi token. Khi JWT đã phát hành, quyền thường tồn tại đến `exp` trừ khi có introspection, revocation hay kiểm tra trạng thái bổ sung.

**Lưu ý quan trọng:** `access token` có thể đại diện cho user hoặc client credentials. Một scope `orders.write` trong token của service account không mặc nhiên cho phép thao tác như nhân viên; authorization có thể cần kiểm tra loại principal, client ID và tài nguyên mục tiêu, ngoài authority chuẩn.

## 11. Nạp quyền từ DB, LDAP và custom provider

### 11.1. Local database

Với username/password, server thường xác minh password qua `DaoAuthenticationProvider` / `PasswordEncoder` và nạp quyền bằng `UserDetailsService`. Bảng quan hệ tối thiểu có thể mô tả:

~~~text
users(user_id, tenant_id, username, password_hash, enabled)
user_grants(user_id, tenant_id, grant_code)
~~~

Ở adapter DB:
- Query quyền theo **internal user_id và tenant_id đã xác minh**, không lấy `userId` hay `tenantId` tùy ý từ body.
- Kiểm tra `enabled`, locked, expired và policy cấm đăng nhập trước khi cấp quyền.
- Chuyển mã `grant_code` thành `RawGrant(Source.LOCAL_DB, value)` rồi gọi normalizer.
- Không dùng `SELECT * FROM user_grants WHERE username = ?` từ giá trị client mà thiếu ràng buộc định danh/tenant.
- Chỉ ghi nhận mã quyền đã biết; quyền lạ do dữ liệu migration lỗi phải được audit.

### 11.2. LDAP hoặc directory group

LDAP group như `cn=Support,ou=Groups,dc=example,dc=org` cần ánh xạ riêng theo DN/group ID ổn định của directory tin cậy. Đừng suy ra `ROLE_ADMIN` chỉ vì DN chứa chữ `Admin`. Kiểm tra referrals, group lồng nhau, mối quan hệ với OU và kết quả truy vấn; group name trùng ở hai directory không nhất thiết có cùng ngữ nghĩa.

Nếu dùng Spring Security LDAP, có thể áp dụng mapper hoặc `LdapAuthoritiesPopulator`/adapter phía xác thực, rồi đưa về canonical authority. Nguồn LDAP nên là một `Source` riêng, không ngụy trang thành `LOCAL_DB`.

### 11.3. Custom AuthenticationProvider

Provider cho OTP, API key, certificate hoặc signed challenge chỉ xác minh bằng giao thức của mình. Sau thành công, nó có thể lấy grants từ record server-side và đưa qua cùng `AuthorityNormalizer`. Không nên tái sử dụng tên authority do client đưa vào cùng request OTP.

Ví dụ:

~~~text
CustomApiKeyProvider.authenticate(...)
  -> xác minh hash/API key record
  -> xác định serviceAccountId, tenantId, active
  -> đọc policy của service account
  -> normalize grants từ nguồn SERVICE_ACCOUNT đã duyệt
  -> trả Authentication trusted (principal + authorities)
~~~

Chú ý: mã `Source` của bài thực hành chỉ bao gồm ba nguồn. Khi thêm `SERVICE_ACCOUNT` hoặc `LDAP_GROUP` trong production, phải **bổ sung enum + bảng mapping + test** minh thị. Không tái sử dụng mapping DB cho mọi nguồn mới.

## 12. Nhiều cơ chế không có nghĩa tự động cộng mọi quyền

Một số hệ thống cùng hỗ trợ login local, OIDC và API token. Có hai mô hình:

**Một cơ chế cho mỗi phiên/request.** Request đã đăng nhập local dùng canonical authorities từ DB. Request bearer JWT dùng canonical authorities từ token phù hợp. Hai luồng có thể cấp cùng một permission nhưng không cần gộp danh sách của hai phiên.

**Tổng hợp nhiều nguồn cho cùng identity.** Ứng dụng có policy rõ ràng cho việc gộp DB + IdP group + scope, và đã xác minh tất cả các grants thuộc về **cùng account, cùng tenant và cùng security principal**. Khi đó mới có thể áp dụng phép hợp (union) sau khi mapping.

Những lỗi nghiêm trọng cần tránh:

~~~text
OIDC issuer A, sub=123   +   JWT issuer B, sub=123
         !=               cùng người (chưa chứng minh)

User tenant-a + group admin của tenant-b
         !=               ROLE_ADMIN trong tenant-a

Session user A + JWT bearer token user B
         !=               quyền hợp của A và B

Account disabled + quyền IdP còn hiệu lực
         !=               người dùng được đăng nhập lại
~~~

Dù hai nguồn đều hợp lệ về chữ ký hoặc mật khẩu, việc **liên kết danh tính** là một quyết định bảo mật riêng. Nếu muốn hợp nhất, phải có quy trình xác minh liên kết và quy tắc xử lý khi nguồn mâu thuẫn.

### Quy tắc ưu tiên khi nguồn mâu thuẫn

Ví dụ DB đánh dấu account `disabled` nhưng IdP vẫn trả `groups/operators`. Nếu chính sách của ứng dụng yêu cầu tài khoản nội bộ phải được kích hoạt, **không** được tổng hợp `ROLE_OPERATOR` rồi cho phép truy cập. Kiểm tra trạng thái account là một bước veto **trước** khi cấp authority; Spring Security không tự coi một authority chuỗi `DENY_LOGIN` có hiệu lực ưu tiên hơn `ROLE_OPERATOR`.

Tương tự, tài khoản có quyền “read” ở nguồn A và “write” ở nguồn B không tự nhiên được “write” ở mọi tenant. Policy tổng hợp phải mô tả phạm vi, loại chủ thể và tài nguyên được áp dụng.

## 13. Authority không thay thế kiểm tra quyền trên tài nguyên

Canonical authority `orders:read` thường chỉ thể hiện “được phép yêu cầu đọc đơn hàng”. Nó chưa quyết định **đơn hàng nào** được đọc.

Ví dụ chính sách Servlet:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/orders/**")
        .hasAuthority("orders:read")
    .requestMatchers(HttpMethod.POST, "/orders/**")
        .hasAuthority("orders:write")
    .anyRequest().authenticated()
);
~~~

Đây là **đoạn cấu hình** cần đặt trong `SecurityFilterChain`; còn thiếu imports và các route cần thiết của ứng dụng. Nó kiểm tra loại hành động ở mức URL; controller/service vẫn phải kiểm tra `order.tenantId` và quy tắc ownership.

Ví dụ với method security:

~~~java
@PreAuthorize("hasAuthority('orders:read')")
public OrderDetails getOrder(String orderId) {
    // Service phải kiểm tra tenant và quyền xem đúng orderId.
    return loadAndAuthorizeOrder(orderId);
}
~~~

Đoạn này chỉ mang tính minh họa, cần `@EnableMethodSecurity` và service thật. Nếu phương thức chỉ có `@PreAuthorize("hasAuthority('orders:read')")` mà truy vấn tùy ý theo `orderId`, người dùng có thể xem đơn hàng của tenant khác. Authorization đầy đủ cần kiểm tra thuộc tính của resource và principal; với yêu cầu phức tạp, dùng `AuthorizationManager` hoặc policy service có kiểm soát.

**Role hierarchy** nếu được dùng cũng là chính sách có chủ đích: `ROLE_ADMIN > ROLE_SUPPORT` có thể làm người có role admin nhận các quyền support theo cấu hình. Đừng mặc định rằng các role có quan hệ thứ bậc chỉ vì tên gọi. Khi thay đổi hierarchy phải test lại tất cả endpoint và method liên quan.

## 14. Các bẫy phổ biến khi chuẩn hóa quyền

| Sai lầm | Hậu quả | Thiết kế đúng |
| --- | --- | --- |
| Gắn `ROLE_` vào mọi giá trị bên ngoài | Một raw claim `ADMIN` có thể thành `ROLE_ADMIN` | Source-specific allowlist, không nối chuỗi mù |
| Coi `scope` là role của user | Service token có thể nhận quyền người dùng ngoài dự kiến | Phân biệt scope, user role, client identity |
| Dịch `SCOPE_orders.read` thành `ROLE_ADMIN` dựa vào tên gần giống | Leo thang quyền | Ánh xạ quyền nghiệp vụ rõ ràng |
| Dùng `equalsIgnoreCase` cho group/scope không kiểm chứng | Nguồn có thể phân biệt case, làm rộng phạm vi | So khớp exact hoặc quy tắc canonicalization từ nguồn |
| Tự `trim`/decode mọi giá trị | Chuỗi không hợp lệ có thể được chấp nhận ngoài hợp đồng | Reject nếu đầu vào không đúng format |
| Gộp grants từ hai `sub` cùng chuỗi nhưng khác issuer | Ghép nhầm identity, cộng quyền | Liên kết trên định danh issuer+sub đã xác minh |
| Gộp quyền tenant A với tenant B | Truy cập chéo tổ chức | Ràng buộc tenant trong subject, grants và resource |
| Tin JSON `roles` từ frontend | Client tự chỉ định quyền | Chỉ lấy từ adapter nguồn đáng tin |
| Dùng `GrantedAuthority("DENY")` để mong phủ định quyền khác | Chuỗi deny không có ý nghĩa veto mặc định | Kiểm tra account state và policy deny riêng |
| Không kiểm tra audience của JWT | Token phát cho hệ thống khác bị tái dùng | Cấu hình validator issuer/audience/token purpose |
| Thay role DB nhưng quên session đang sống | Quyền cũ tiếp tục có hiệu lực | Thiết kế refresh/revoke/invalidate session |
| JWT dài hạn giữ scope đã bị thu hồi | Quyền cũ vẫn hoạt động tới khi token hết hạn | TTL phù hợp, revocation/introspection khi cần |
| Đổi tên `SCOPE_` sang authority riêng mà không cập nhật rule | Người dùng hợp lệ bị 403 hoặc được cấp sai | Test ma trận rule trước và sau migration |
| Chỉ test một trường hợp được cấp quyền | Không thấy nguy cơ role lạ trở thành admin | Thêm test âm tính cho nguồn, issuer, tenant và quyền |
| Lưu các tên quyền chỉ trong code mà không version | Khó audit và thay đổi an toàn | Policy version, kiểm thử và quy trình phê duyệt |

## 15. Vòng đời của quyền và tính nhất quán

Hãy quyết định khi nào authority được làm mới:

| Cơ chế | Authority có thể được chốt lúc nào? | Cách cập nhật |
| --- | --- | --- |
| Username/password + HTTP session | Khi đăng nhập, rồi lưu trong `SecurityContext` | Refresh theo policy, đăng xuất/hủy phiên, reauthentication |
| OAuth2/OIDC login + session | Khi hoàn tất login và nạp groups | Lấy lại thông tin/reauthenticate; cân nhắc lifecycle của IdP |
| JWT Resource Server | Mỗi request giải JWT nhưng scope trong token là snapshot | Token mới hoặc thu hồi token, thời hạn `exp` ngắn phù hợp |
| API key / service principal | Mỗi request hoặc theo cache | Kiểm tra trạng thái key, thu hồi và invalidation cache |
| Local DB permission | Khi adapter đọc DB | Đảm bảo transaction/caching và invalidation theo yêu cầu |

Ở các quyền nhạy cảm như `ROLE_ADMIN`, có thể cần tra cứu trạng thái account tức thời hoặc một phiên bản policy thay vì chỉ tin quyền đã lưu lâu trong session/JWT. Đừng tối ưu cache trước khi xác định mức độ chấp nhận độ trễ thu hồi quyền.

**Audit nên ghi được:** principal nội bộ, tenant, cơ chế auth, issuer/client, mapping version, authority sau chuẩn hóa, và nguyên nhân quyền bị từ chối (nếu an toàn để log). Không ghi raw password, access token, refresh token hoặc secret.

## 16. Quy trình triển khai trong dự án thật

1. **Liệt kê đường xác thực:** local password, OIDC, LDAP, bearer JWT, API key, service principal. Ghi nơi xác thực và nơi nạp quyền của từng đường.
2. **Định nghĩa canonical authorities:** naming convention, prefix `ROLE_`, permission như `orders:read` và ma trận endpoint/method cần quyền nào.
3. **Thiết kế mapping theo nguồn:** cho mỗi issuer/tenant cần thiết, ghi giá trị raw được phép, canonical value, owner phê duyệt, version và cách thu hồi.
4. **Đặt trust boundary:** adapter chỉ nạp dữ liệu sau khi đã kiểm tra credential/token/issuer/audience/subject và account status.
5. **Dùng chung service normalize:** mọi provider và converter dùng cùng policy; không duy trì hai bản mapper khác nhau trừ khi có quy tắc tách biệt được tài liệu hóa.
6. **Giữ provenance để kiểm toán:** phân biệt DB grant, IdP group và JWT scope khi điều tra sự cố; kết quả `SimpleGrantedAuthority` không chứa đủ dữ liệu nguồn.
7. **Tách authorization theo tài nguyên:** permission chuẩn phải được kết hợp với tenant, ownership, trạng thái đơn hàng và các quy tắc nghiệp vụ khác.
8. **Test positive/negative:** đúng quyền, sai nguồn, case mismatch, quyền thừa, tenant khác, issuer khác, account disabled, token hết hạn, quyền thay đổi khi session/JWT đã phát hành.
9. **Triển khai và quan sát:** đo số unmapped grants, tỉ lệ 403, lỗi issuer/tenant, phiên còn quyền cũ; cập nhật policy qua review thay vì nhận mọi group mới tự động.
10. **Di trú không gián đoạn:** khi đổi từ `SCOPE_orders.read` sang `orders:read`, rà lại filter, method security, integration test và dữ liệu quyền; không cấp đồng thời nhiều alias vô thời hạn nếu không có nhu cầu.

### Một ma trận kiểm thử thực tế

| Định danh | Dữ liệu nguồn | Chính sách mong đợi |
| --- | --- | --- |
| User A, tenant A | DB `role:support` | `ROLE_SUPPORT` |
| User A, tenant A | OIDC `groups/order-readers` | `orders:read` |
| Service B | JWT `orders.read` đúng issuer/audience | `orders:read`, không có `ROLE_SUPPORT` |
| User C | JWT `admin` không được duyệt | Không có `ROLE_ADMIN` |
| User D | IDP group của tenant B, request tenant A | Không cộng quyền tenant B |
| User E | DB account disabled, IdP group còn hiệu lực | Chặn theo policy tài khoản |
| User F | JWT hết hạn hoặc sai audience | Authentication thất bại trước normalize |
| User G | DB và OIDC cấp cùng `orders:read` | Một authority `orders:read` |
| User H | Claim `ORDERS.READ` khác case policy | Không cấp quyền nếu không có mapping |
| User I | Đã thu hồi `orders:write` sau login | Quyền phải bị thu hồi theo policy session/token đã chọn |

## 17. Câu hỏi tự kiểm tra

1. Vì sao `ROLE_SUPPORT` và `SCOPE_support` không tự động giống nhau?
2. Tại sao không nên ánh xạ mọi group bên ngoài bằng `"ROLE_" + group.toUpperCase()`?
3. `GrantedAuthority` biểu diễn được “deny account” có ưu tiên hơn các role khác không?
4. Khi nào có thể gộp grants từ DB, IdP và JWT cho một user? Những điều kiện về subject/issuer/tenant cần thỏa?
5. Trong `hasRole("SUPPORT")`, Spring Security thường tìm chuỗi authority nào?
6. Khác nhau giữa `JwtGrantedAuthoritiesConverter` và `GrantedAuthoritiesMapper` dùng trong OAuth2 Login là gì?
7. Tại sao user có `orders:read` vẫn có thể bị chặn xem một order của tenant khác?
8. Nếu role thay đổi sau khi session/JWT đã được cấp, điều gì quyết định quyền cũ còn được dùng bao lâu?
9. Tại sao test case `JwtScope("admin")` không map thành `ROLE_ADMIN` là quan trọng?
10. Vì sao không thể dùng chung `sub` trần từ hai issuer khác nhau để cộng quyền?

## 18. Tài liệu tham khảo

1. Spring Security — Authorization Architecture, `GrantedAuthority` và `ROLE_`: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
2. Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
3. Spring Security — OAuth2 Login Advanced Configuration, mapping authorities: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
4. Spring Security — OAuth2 Resource Server JWT, scope và authorities: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
5. Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
6. Spring Security API — `GrantedAuthoritiesMapper`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/authority/mapping/GrantedAuthoritiesMapper.html
7. Spring Security API — `JwtAuthenticationConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html
8. Spring Security API — `SimpleGrantedAuthority`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/authority/SimpleGrantedAuthority.html

**Nguyên tắc cần nhớ:** quyền trong Spring Security phải được tạo từ **danh tính đã xác minh và nguồn cấp quyền được phép**, rồi ánh xạ qua **chính sách chuẩn hóa tường minh**. Việc nhiều cơ chế cung cấp các chuỗi giống nhau không tự chứng minh đó là cùng user, cùng tenant hoặc cùng mức quyền.
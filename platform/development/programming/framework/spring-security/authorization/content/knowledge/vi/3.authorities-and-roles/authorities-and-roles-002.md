# SimpleGrantedAuthority và ý nghĩa chuỗi định danh quyền

Trong Spring Security, **`SimpleGrantedAuthority`** là cách biểu diễn một **quyền (authority) bằng chuỗi ký tự**. Ví dụ `ROLE_ADMIN`, `reports.read` hay `SCOPE_orders.read` đều có thể được lưu bằng cùng một lớp:

```java
GrantedAuthority admin = new SimpleGrantedAuthority("ROLE_ADMIN");
GrantedAuthority read = new SimpleGrantedAuthority("reports.read");
GrantedAuthority scope = new SimpleGrantedAuthority("SCOPE_orders.read");
```

Điểm cần nắm: **`SimpleGrantedAuthority` không tự cấp quyền, tự xác thực người dùng hay quyết định một request được truy cập**. Nó chỉ giữ một chuỗi định danh mà các thành phần authorization sẽ so khớp theo quy tắc đã cấu hình. Chuỗi khác nhau có thể mang ý nghĩa nghiệp vụ khác nhau, nhưng Java object vẫn cùng loại `SimpleGrantedAuthority`.

## 1. GrantedAuthority và SimpleGrantedAuthority khác gì nhau?

### 1.1. `GrantedAuthority` là hợp đồng chung

`GrantedAuthority` là interface của Spring Security, biểu diễn một quyền được gắn với chủ thể đã xác thực. Phương thức cốt lõi:

```java
public interface GrantedAuthority extends java.io.Serializable {
    String getAuthority();
}
```

`getAuthority()` trả về **biểu diễn bằng chuỗi** của quyền nếu quyền có thể biểu diễn như vậy. Với những implementation tùy biến có quyền phức tạp không biểu diễn đủ bằng chuỗi, phương thức có thể trả `null` và authorization component tương ứng cần hiểu loại quyền đó. Với `SimpleGrantedAuthority`, chuỗi do constructor nhận chính là giá trị trả về.

### 1.2. `SimpleGrantedAuthority` là implementation đơn giản

Có thể hiểu logic quan trọng của lớp như sau (mã khái quát, không sao chép toàn bộ mã thư viện):

```java
public final class SimpleGrantedAuthority implements GrantedAuthority {
    private final String authority;

    public SimpleGrantedAuthority(String authority) {
        // Spring Security thực tế kiểm tra chuỗi có ký tự khác whitespace.
        this.authority = authority;
    }

    @Override
    public String getAuthority() {
        return authority;
    }
}
```

Đoạn khái quát trên **không phải lớp để tự biên dịch trong project**; import lớp thật qua `org.springframework.security.core.authority.SimpleGrantedAuthority`. Bản triển khai thực tế còn có `equals`, `hashCode`, `toString` và kiểm tra đầu vào.

Các tính chất cần nhớ:

- Constructor nhận **chuỗi không null, không rỗng và không chỉ có khoảng trắng**; giá trị không hợp lệ gây `IllegalArgumentException`.
- Constructor **không tự thêm `ROLE_` hay `SCOPE_`**, không tự đổi chữ thường/chữ hoa và không chuẩn hóa nội dung để phù hợp policy.
- `getAuthority()` trả lại đúng chuỗi đã cung cấp, bao gồm tiền tố và ký tự phân biệt chữ hoa/chữ thường.
- Hai đối tượng `SimpleGrantedAuthority` có **cùng chuỗi** thì bằng nhau theo `equals` và có cùng `hashCode`; có thể dùng trong `Set` để khử trùng lặp theo chuỗi.
- Tên trường nội bộ trong thư viện có thể là “role”, nhưng **đối tượng không bắt buộc chứa role**; nó có thể chứa permission hoặc scope.

Ví dụ:

| Khởi tạo | `getAuthority()` | Ý nghĩa do ứng dụng quy ước |
| --- | --- | --- |
| `new SimpleGrantedAuthority("ROLE_ADMIN")` | `ROLE_ADMIN` | Role quản trị theo quy ước mặc định |
| `new SimpleGrantedAuthority("ROLE_USER")` | `ROLE_USER` | Role người dùng |
| `new SimpleGrantedAuthority("documents.read")` | `documents.read` | Quyền đọc tài liệu |
| `new SimpleGrantedAuthority("orders:approve")` | `orders:approve` | Quyền duyệt đơn |
| `new SimpleGrantedAuthority("SCOPE_orders.read")` | `SCOPE_orders.read` | Scope OAuth2 được ánh xạ thành authority |
| `new SimpleGrantedAuthority("ADMIN")` | `ADMIN` | Một authority hợp lệ về mặt cú pháp, **không phải** `ROLE_ADMIN` |
| `new SimpleGrantedAuthority("role_admin")` | `role_admin` | Một chuỗi khác với `ROLE_ADMIN` |

Chuỗi là **định danh quyền**, không phải mô tả tự nhiên hay đối tượng policy đầy đủ. Tên `orders:approve` chỉ có tác dụng khi hệ thống thống nhất quy ước và có rule kiểm tra chính xác chuỗi đó.

## 2. Chuỗi định danh quyền được so khớp thế nào?

Trong các cơ chế cơ bản của Spring Security, `Authentication` có tập `GrantedAuthority`; rule như `hasAuthority("documents.read")` kiểm tra có authority phù hợp trong tập đó không.

Ví dụ, người dùng có các authority:

```text
ROLE_MANAGER
documents.read
SCOPE_orders.read
```

Khi dùng quy tắc so khớp mặc định:

| Rule | Chuỗi cần có | Kết quả với tập trên |
| --- | --- | --- |
| `hasAuthority("documents.read")` | `documents.read` | **Cho phép** |
| `hasAuthority("DOCUMENTS.READ")` | `DOCUMENTS.READ` | **Từ chối** |
| `hasAuthority("ROLE_MANAGER")` | `ROLE_MANAGER` | **Cho phép** |
| `hasAuthority("MANAGER")` | `MANAGER` | **Từ chối** |
| `hasAuthority("SCOPE_orders.read")` | `SCOPE_orders.read` | **Cho phép** |
| `hasAuthority("orders.read")` | `orders.read` | **Từ chối** |
| `hasRole("MANAGER")` | `ROLE_MANAGER` (mặc định) | **Cho phép** |
| `hasRole("ADMIN")` | `ROLE_ADMIN` (mặc định) | **Từ chối** |

**Mặc định, authority được so khớp như chuỗi chính xác và phân biệt chữ hoa/chữ thường.** Không có quy tắc tự hiểu “`MANAGER` đồng nghĩa `ROLE_MANAGER`”, “`read` đồng nghĩa `READ`”, hoặc “`orders.read` đồng nghĩa `SCOPE_orders.read`”.

Các cấu hình tùy chỉnh như **role hierarchy**, custom authorization manager hoặc mapping authority có thể mở rộng hành vi. Khi phân tích lỗi, cần phân biệt kết quả so khớp một chuỗi trực tiếp với kết quả policy cuối cùng có thể bao gồm các bước chuyển đổi hoặc kế thừa.

### Vì sao phải thống nhất tên quyền?

Nếu nơi cấp quyền gắn `DOC_READ` nhưng nơi kiểm tra gọi `hasAuthority("documents.read")`, hệ thống sẽ từ chối dù lập trình viên tưởng cả hai đều có nghĩa “đọc tài liệu”. Ngược lại, nếu một bước mapping vô tình cấp `ROLE_ADMIN` cho người chỉ có scope `admin`, chính sách có thể cho phép nhiều hơn dự kiến.

Vì vậy cần một **hợp đồng định danh quyền** được kiểm soát: tên chuẩn, ai được cấp, nguồn dữ liệu, điều kiện hiệu lực, vị trí so khớp và cách cập nhật. Không diễn giải ý nghĩa bảo mật chỉ bằng cách nhìn từ khóa “admin”, “read”, “write” trong chuỗi.

## 3. Phân biệt authority, role và permission

`SimpleGrantedAuthority` là **kiểu chứa dữ liệu**; role và permission là **ý nghĩa nghiệp vụ hoặc quy ước** gán cho dữ liệu.

- **Authority:** chuỗi mà Spring Security dùng trong quá trình authorization, chẳng hạn `ROLE_ADMIN` hoặc `invoices.approve`.
- **Role:** một nhóm quyền/khái niệm về vị trí người dùng, thường có tiền tố `ROLE_` khi dùng `hasRole` mặc định. Ví dụ `ROLE_ADMIN`.
- **Permission:** khả năng thực hiện một hành động cụ thể, ví dụ `invoice:read`, `invoice:approve`. Đây cũng có thể được biểu diễn bằng `SimpleGrantedAuthority`.
- **OAuth2 scope:** phạm vi mà OAuth2 Authorization Server cấp cho client/token; với JWT Resource Server và converter mặc định thường được chuyển thành authority có tiền tố `SCOPE_`.

**Không có lớp riêng bắt buộc cho “role”** khi kiểm tra bằng `hasRole`. Role mặc định cũng được lưu như một `GrantedAuthority` có chuỗi `ROLE_...`.

Ví dụ **chỉ là dữ liệu**, chưa phải một người dùng được xác thực:

```java
List<GrantedAuthority> granted = List.of(
    new SimpleGrantedAuthority("ROLE_ACCOUNTANT"),
    new SimpleGrantedAuthority("invoice:read"),
    new SimpleGrantedAuthority("invoice:approve")
);
```

Một user có role `ROLE_ACCOUNTANT` **không tự động** có `invoice:approve` chỉ vì tên role nghe liên quan. Ứng dụng cần ánh xạ role → permission tại bước tạo Authentication, cấu hình role hierarchy phù hợp hoặc sử dụng rule có khai báo rõ.

### `hasRole` khác `hasAuthority`

Giả sử đã có:

```java
new SimpleGrantedAuthority("ROLE_ADMIN")
```

Hai rule sau thường diễn đạt cùng yêu cầu **với quy ước tiền tố mặc định**:

```java
.hasRole("ADMIN")
.hasAuthority("ROLE_ADMIN")
```

`hasRole("ADMIN")` là cách viết thuận tiện với tiền tố role mặc định `ROLE_`; `hasAuthority("ROLE_ADMIN")` so khớp đúng chuỗi được truyền. **Không tự thêm `ROLE_` khi tạo `SimpleGrantedAuthority` từ chuỗi role mà nguồn đã cung cấp tiền tố đó**, và cũng không mặc định truyền `ROLE_ADMIN` vào API `hasRole` vốn thường mong tên role chưa có tiền tố.

Ở phần mềm cấu hình lại prefix hoặc dùng `RoleHierarchy`, hãy đối chiếu chính sách thực tế thay vì suy luận mọi nơi đều xử lý giống nhau. Trong bài này, các ví dụ đều dùng tiền tố mặc định.

## 4. Chuỗi quyền đến từ đâu?

Bản thân `SimpleGrantedAuthority` **không đi tìm quyền** từ database, JWT hay request. Quyền được tạo bởi các bước xác thực/ánh xạ đã được cấu hình.

### 4.1. Người dùng đăng nhập bằng username/password

Một `UserDetailsService` hoặc `AuthenticationProvider` có thể lấy role/permission từ database và biến chúng thành `GrantedAuthority`. Với builder `UserDetails` của Spring Security:

```java
UserDetails user = User.withUsername("alice")
    .password(encodedPassword)
    .roles("ADMIN")
    .build();
```

Dưới quy ước mặc định, `roles("ADMIN")` tạo authority `ROLE_ADMIN`. Ngược lại, `authorities("ROLE_ADMIN", "invoices.read")` nhận **tên authority trực tiếp**. `encodedPassword` ở đây là biến từ logic cấu hình khác, không phải chuỗi mật khẩu mẫu để chạy độc lập.

Không nên trộn quyền do client tự gửi trong HTTP body với quyền đáng tin trong `Authentication`. Bước xác thực và mapping phải lấy dữ liệu từ kho được phép tin.

### 4.2. JWT OAuth2 Resource Server

Khi ứng dụng là OAuth2 Resource Server, `JwtAuthenticationConverter` có thể ánh xạ claims `scope` hoặc `scp` thành granted authorities. Với cấu hình mặc định thông dụng:

```json
{
  "sub": "alice",
  "scope": "orders.read orders.write"
}
```

Các authority tương ứng thường là:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Do đó API bảo vệ bằng `hasAuthority("SCOPE_orders.read")` (hoặc cơ chế tiện ích chuyên cho scope) mới khớp. `hasRole("orders.read")` mặc định tìm `ROLE_orders.read`, **không** phải `SCOPE_orders.read`.

**Cần nhớ:** JSON trên chỉ mô tả payload minh họa. Trong ứng dụng thật, Spring Security phải **xác thực token** và kiểm tra issuer, audience cùng những điều kiện liên quan trước khi tin claims. Không lấy trực tiếp `scope` do một HTTP header hay request body tự khai rồi gán authority.

`JwtGrantedAuthoritiesConverter` có thể được tùy chỉnh prefix, claim name hoặc cách tách scopes. Khi tùy chỉnh, kiểm lại các rule kiểm quyền để không lệch tên.

### 4.3. Hệ thống đăng nhập hoặc identity provider bên ngoài

Role trong IdP có thể tên là `admin`, `ADMIN`, `app-admin`, hoặc được đặt trong claim riêng. Đây **không mặc nhiên là** `ROLE_ADMIN`. Một lớp mapping rõ ràng có thể chuyển claim đã xác minh thành tên authority chuẩn mà **chỉ những nguồn tin cậy** mới được phép cấp.

Ví dụ mapping khái niệm:

```text
IdP role "application-admin"
     ↓ xác minh token, issuer, audience và quyền được phép cấp
Application mapping
     ↓
SimpleGrantedAuthority("ROLE_APP_ADMIN")
     ↓
Authorization rule hasRole("APP_ADMIN")
```

Không tự coi mọi claim `roles`, `groups` hoặc `scope` từ mọi issuer là quyền nội bộ ngang nhau. Một scope công khai có thể có ý nghĩa hoàn toàn khác với quyền quản trị tổ chức.

## 5. Ví dụ Java 17 chạy được: nhìn chính xác chuỗi được giữ và so khớp

Ví dụ này dùng **chính lớp `SimpleGrantedAuthority` của Spring Security**, qua dependency Maven `spring-security-core`. Chương trình tạo danh sách quyền tin cậy giả lập, so khớp chuỗi và in kết quả. Nó **không phải trình xác thực**, không thiết lập HTTP security và không cấp quyền cho một phiên đăng nhập thật.

Cấu trúc thư mục:

```text
authority-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AuthorityDemo.java
```

Tạo file **`pom.xml`** trong `authority-demo`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>authority-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-core</artifactId>
            <version>6.5.11</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.AuthorityDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo **`src/main/java/demo/AuthorityDemo.java`**:

```java
package demo;

import java.util.List;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public class AuthorityDemo {

    static boolean containsAuthority(
            List<? extends GrantedAuthority> granted,
            String required
    ) {
        return granted.stream()
                .anyMatch(authority ->
                        required.equals(authority.getAuthority()));
    }

    // Chỉ mô phỏng quy ước ROLE_ mặc định.
    // Đây KHÔNG phải toàn bộ cơ chế hasRole của Spring Security.
    static boolean containsDefaultRole(
            List<? extends GrantedAuthority> granted,
            String role
    ) {
        return containsAuthority(granted, "ROLE_" + role);
    }

    public static void main(String[] args) {
        List<GrantedAuthority> granted = List.of(
                new SimpleGrantedAuthority("ROLE_ADMIN"),
                new SimpleGrantedAuthority("invoices.approve"),
                new SimpleGrantedAuthority("SCOPE_invoices.read")
        );

        System.out.println("stored: " + granted.get(0).getAuthority());
        System.out.println("same text equal: "
                + new SimpleGrantedAuthority("ROLE_ADMIN").equals(granted.get(0)));
        System.out.println("authority ROLE_ADMIN: "
                + containsAuthority(granted, "ROLE_ADMIN"));
        System.out.println("authority ADMIN: "
                + containsAuthority(granted, "ADMIN"));
        System.out.println("default role ADMIN: "
                + containsDefaultRole(granted, "ADMIN"));
        System.out.println("permission invoices.approve: "
                + containsAuthority(granted, "invoices.approve"));
        System.out.println("permission INVOICES.APPROVE: "
                + containsAuthority(granted, "INVOICES.APPROVE"));
        System.out.println("scope SCOPE_invoices.read: "
                + containsAuthority(granted, "SCOPE_invoices.read"));
        System.out.println("scope invoices.read: "
                + containsAuthority(granted, "invoices.read"));
    }
}
```

Yêu cầu **JDK 17+ và Maven 3.x/4.x tương thích**. Trong thư mục `authority-demo` chạy:

```bash
mvn -q compile exec:java
```

Kết quả stdout của chương trình:

```text
stored: ROLE_ADMIN
same text equal: true
authority ROLE_ADMIN: true
authority ADMIN: false
default role ADMIN: true
permission invoices.approve: true
permission INVOICES.APPROVE: false
scope SCOPE_invoices.read: true
scope invoices.read: false
```

Từ kết quả trên:

1. Đối tượng giữ đúng `ROLE_ADMIN`, không biến thành `ADMIN` khi gọi `getAuthority()`.
2. Hai `SimpleGrantedAuthority("ROLE_ADMIN")` có nội dung bằng nhau theo `equals`, dù là hai object khác nhau.
3. `ROLE_ADMIN` và `ADMIN` không bằng nhau; helper mô phỏng `hasRole("ADMIN")` theo tiền tố mặc định mới tìm ra `ROLE_ADMIN`.
4. `invoices.approve` khác `INVOICES.APPROVE` vì so khớp phân biệt hoa/thường.
5. `SCOPE_invoices.read` khác `invoices.read`. Prefix phải được tính đến khi thiết kế rule.

**Phạm vi của ví dụ:** `containsAuthority` chỉ mô phỏng việc so khớp tên trong danh sách; Spring Security thực tế còn kiểm tra `Authentication`, anonymous/unauthenticated state, các authorization manager và có thể xét role hierarchy hoặc chính sách tùy chỉnh. Không đưa danh sách do client tự tạo vào `Authentication` đã xác thực để bảo vệ API.

## 6. Dùng các authority trong HTTP authorization của Spring Security

Khi ứng dụng Spring Boot Servlet đã cấu hình **authentication** phù hợp (session/JWT/đường xác thực khác), có thể dùng authority ở các rule HTTP. Ví dụ **lớp cấu hình tích hợp** trong ứng dụng Spring Boot 3.x + Spring Security 6.x:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiAccessConfig {

    @Bean
    SecurityFilterChain apiAccess(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/invoices/**")
                    .hasAuthority("SCOPE_invoices.read")
                .requestMatchers(HttpMethod.POST, "/api/invoices/*/approve")
                    .hasAuthority("invoices.approve")
                .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

Đây là **một lớp trong ứng dụng Spring**, không phải Java program chạy độc lập qua `javac`. Nó chỉ mô tả quy tắc ở tầng HTTP. Ứng dụng thực tế cần cấu hình authentication, dependency, filter chain, CSRF/session theo kiến trúc và các tuyến URL thích hợp.

Cách đọc rule:

- `/admin/**` yêu cầu `ROLE_ADMIN` vì `hasRole("ADMIN")` dùng tiền tố mặc định.
- `GET /api/invoices/**` yêu cầu chính xác `SCOPE_invoices.read`, thường đến từ token JWT đã được xác minh và mapping.
- `POST /api/invoices/*/approve` yêu cầu chính xác `invoices.approve`, một permission do ứng dụng chủ động cấp/mapping.
- `anyRequest().denyAll()` chặn các request chưa được khai báo rule. Những endpoint công khai, actuator hoặc luồng login cần được thiết kế riêng khi triển khai thật.

**Không phải bất kỳ `SimpleGrantedAuthority("ROLE_ADMIN")` nào được tạo ở đâu đó trong code cũng tự động được rule trên nhìn thấy.** Đối tượng phải nằm trong `Authentication#getAuthorities()` của request đang được xử lý (hoặc dữ liệu tương đương được authorization manager sử dụng).

### Kiểm soát ở tầng method

Khi bật `@EnableMethodSecurity`, có thể bảo vệ nghiệp vụ bằng `@PreAuthorize`:

```java
@PreAuthorize("hasAuthority('invoices.approve')")
public void approveInvoice(String invoiceId) {
    // Logic xử lý hóa đơn chỉ sau khi kiểm quyền cơ bản.
}
```

Đây là **method minh họa** đặt trong Spring-managed bean có method security, chưa phải một class độc lập. Rule chỉ xác định caller có permission `invoices.approve`; nếu chỉ người sở hữu hoặc đúng tenant mới được duyệt hóa đơn này, cần **thêm kiểm tra trên invoiceId** qua policy/repository đáng tin cậy. Authority dạng chuỗi thường là quyền khái quát, không tự chứng minh quyền trên từng record.

## 7. Các thuộc tính quan trọng của chuỗi authority

### 7.1. Phân biệt chữ hoa, ký tự đặc biệt và khoảng trắng

Giả sử một mapper lưu:

```text
"ROLE_ADMIN"
"role_admin"
"ROLE_ADMIN "
"ROLE_ADMIN"
```

Ba chuỗi đầu là **ba authority khác nhau**; chuỗi cuối trùng chính xác chuỗi đầu. `SimpleGrantedAuthority` không tự `trim()` và không `toUpperCase()`. Chuỗi chỉ gồm whitespace bị từ chối ngay khi khởi tạo.

Nếu hệ thống lưu quyền ở database hoặc nhận từ IdP, nên **chuẩn hóa tại ranh giới dữ liệu** bằng quy tắc thống nhất và kiểm soát mapping, thay vì tùy tiện chuyển tên khi so khớp. Các thay đổi tên quyền phải được xem như thay đổi hợp đồng bảo mật.

### 7.2. `Set` và `List` có thể biểu diễn các authority như nhau

Tạo hai object có cùng chuỗi:

```java
var a = new SimpleGrantedAuthority("invoices.approve");
var b = new SimpleGrantedAuthority("invoices.approve");
```

`a.equals(b)` là `true`. Nếu đặt vào `HashSet<GrantedAuthority>`, hai phần tử tương đương này được gom thành một. Nếu đặt vào `List` thì vẫn có thể chứa cả hai. Việc lặp quyền không nên làm tăng đặc quyền; authorization không coi “hai bản sao một authority” là quyền mạnh hơn.

### 7.3. `getAuthority()` không phải nội dung có thể sửa tùy ý

`SimpleGrantedAuthority` giữ chuỗi trong field cuối cùng (`final`); không có setter để đổi tên quyền trên cùng object. Muốn cập nhật authority cho người dùng trong Authentication/phiên, cần **tạo lại tập quyền theo chính sách và cập nhật đúng cơ chế xác thực**. Đổi quyền trong database không nhất thiết có tác dụng tức thời lên phiên đăng nhập hoặc JWT đã cấp.

### 7.4. Không có suy luận phân cấp từ tên chuỗi

Có `ROLE_ADMIN` không tự động bao hàm `ROLE_USER`; `invoices.*` không tự động khớp `invoices.approve`. Muốn role hierarchy hoặc wildcard permission, phải định nghĩa cơ chế hỗ trợ riêng và kiểm thử nó. Đừng nhầm định danh `"documents.read.*"` với một biểu thức glob/regex do Spring Security tự hiểu.

### 7.5. Chuỗi không chứa đầy đủ ngữ cảnh quyết định

`hasAuthority("documents.read")` chỉ hỏi một permission khái quát. Việc user có thực sự được đọc tài liệu `document-123` có thể cần dữ liệu **owner, tenant, trạng thái và chia sẻ**. Dùng object-level authorization/method security/policy service cho bước này; tránh xem một chuỗi `SimpleGrantedAuthority` như bằng chứng đầy đủ cho mọi bản ghi.

## 8. Cách thiết kế quy ước đặt tên authority

Không có một chuẩn tên bắt buộc cho mọi ứng dụng; điều cần thiết là **nhất quán** giữa nơi cấp, nơi chuyển đổi và nơi kiểm tra.

Một quy ước thường dùng:

| Nhóm | Ví dụ | Nguyên tắc |
| --- | --- | --- |
| Role nội bộ | `ROLE_ADMIN`, `ROLE_SUPPORT` | Dùng tiền tố `ROLE_` khi rule dùng `hasRole` mặc định |
| Permission nghiệp vụ | `invoice:read`, `invoice:approve` | Dùng `hasAuthority` và khai báo rõ ai được cấp |
| Scope OAuth2 | `SCOPE_orders.read` | Chỉ khi converter tạo prefix `SCOPE_`; kiểm theo contract token |
| Quyền theo module | `billing.invoice.export` | Định danh có namespace để tránh xung đột |
| Rule theo object | `canReadInvoice(user, invoiceId)` | Thực thi bằng policy động, không cố nhét mọi object ID vào chuỗi authority |

Ví dụ ánh xạ role sang permission ở bước tạo Authentication:

```text
ROLE_ACCOUNTANT -> invoice:read
ROLE_APPROVER   -> invoice:read, invoice:approve
ROLE_AUDITOR    -> invoice:read, audit:read
```

Đây là **hợp đồng nghiệp vụ minh họa**, không phải tính năng tự động của `SimpleGrantedAuthority`. Mapping có thể được thực hiện trong service xác thực hoặc policy layer, nhưng phải được bảo vệ khỏi việc user tự cấp role.

Khi có nhiều issuer/tenant, đặt rõ namespace hoặc check issuer và tenant trước mapping; tên quyền giống nhau từ hai hệ thống khác nhau **không đảm bảo** ngữ nghĩa và mức tin cậy giống nhau.

## 9. Những lỗi phổ biến và cách xác định nguyên nhân

| Biểu hiện | Nguyên nhân khả dĩ | Cách kiểm tra/sửa |
| --- | --- | --- |
| Có `ADMIN` nhưng `hasRole("ADMIN")` từ chối | Authority đang lưu `ADMIN` thay vì `ROLE_ADMIN` | Kiểm chính xác `Authentication#getAuthorities()`; thống nhất mapping |
| Có `ROLE_ADMIN` nhưng `hasAuthority("ADMIN")` từ chối | `hasAuthority` không tự thêm prefix | Dùng `hasAuthority("ROLE_ADMIN")` hoặc `hasRole("ADMIN")` |
| JWT có `orders.read` nhưng rule `hasAuthority("orders.read")` từ chối | Converter tạo `SCOPE_orders.read` | Xem mapping thực tế và dùng đúng chuỗi |
| Quyền từ DB là `report.read` nhưng policy là `REPORT.READ` | Phân biệt hoa/thường | Chuẩn hóa contract tại nguồn |
| Quyền có space cuối không khớp | Chuỗi đã được lưu kèm whitespace | Kiểm tra dữ liệu/mapping; không âm thầm bỏ khoảng trắng trong policy |
| Thêm `new SimpleGrantedAuthority(...)` trong code nhưng quyền request không đổi | Object không nằm trong Authentication đang dùng | Xác minh authentication pipeline, tránh tạo object rời |
| Thêm `ROLE_ADMIN` rồi tưởng có `ROLE_USER` | Chưa khai báo role hierarchy/mapping | Cấu hình role hierarchy hoặc cấp đúng authority |
| User bị hạ quyền nhưng token cũ vẫn được chấp nhận | JWT/session đang giữ claims/authorities cũ | Thiết kế session invalidation, token TTL và kiểm tra quyền động phù hợp |
| Kiểm `documents.read` xong đọc tài liệu người khác | Chỉ kiểm quyền khái quát, bỏ ownership/tenant | Thêm resource-level authorization |
| Lấy `roles` từ input HTTP rồi cấp quyền | Tin dữ liệu do caller kiểm soát | Chỉ cấp từ nguồn đáng tin sau xác thực |
| Log ra toàn bộ Bearer token để debug quyền | Rò token và khả năng truy cập | Log danh sách authority đã lọc/anonymize; không ghi token/secret |

**Gợi ý debug an toàn:** tại server sau authentication, kiểm tra loại `Authentication`, tên principal đã xác minh và danh sách `getAuthority()` thực tế theo mức log được phép. So sánh từng chuỗi với rule đã cấu hình, chú ý prefix, chữ hoa/chữ thường và mapping converter. Tránh ghi token nguyên bản hoặc dữ liệu nhạy cảm vào log.

### Không trộn authentication với authorization

- **Authentication** xác minh người dùng/token và tạo `Authentication`.
- **Authority mapping** gắn các `GrantedAuthority` đáng tin vào `Authentication`.
- **Authorization** kiểm rule với danh tính, authorities và các yếu tố policy khác.

Nếu authentication thất bại, vấn đề có thể nằm ở JWT signature/issuer/audience, password/session hoặc authentication provider. Nếu authentication thành công nhưng bị 403, lúc đó hãy kiểm chuỗi authority, logic `hasRole`/`hasAuthority` và rule trên tài nguyên. Phản hồi HTTP thực tế còn phụ thuộc entrypoint/exception handler và cấu hình bảo mật.

## 10. Checklist kiểm thử quan hệ giữa tên quyền và policy

Một bộ kiểm thử vừa đủ để phát hiện lỗi chuẩn hóa và mapping:

1. **Role default:** user có `ROLE_ADMIN`, `hasRole("ADMIN")` cho phép; user chỉ có `ADMIN` không được coi là role `ADMIN` theo mặc định.
2. **Exact string:** `hasAuthority("invoice:approve")` không khớp `invoice:read` hoặc `INVOICE:APPROVE`.
3. **Scope mapping:** token hợp lệ có `scope=orders.read` → expected authority theo converter; rule áp đúng `SCOPE_orders.read` nếu dùng prefix mặc định.
4. **Empty input:** thử tạo `SimpleGrantedAuthority(null)`, `""`, `"   "` đều phải bị từ chối; không lưu giá trị vô nghĩa.
5. **Equality:** hai đối tượng có chuỗi giống nhau bằng nhau; `Set` khử trùng lặp theo định danh.
6. **Hierarchy:** quyền kế thừa chỉ hoạt động khi cấu hình role hierarchy/mapping tương ứng; không mặc định từ tên.
7. **Authentication source:** token/claim do người khác phát hành hoặc không xác minh không được biến thành quyền nội bộ.
8. **Resource boundary:** user có `documents.read` nhưng không sở hữu/không được share tài liệu vẫn bị từ chối ở tầng policy nếu nghiệp vụ yêu cầu.
9. **Revocation:** sửa role trong DB phải có chiến lược cập nhật session/token và cache; kiểm sau khi hết quyền.
10. **Multiple APIs/tenants:** tên authority từ nhiều issuer/tenant không bị trộn ngoài ý muốn.

## 11. Câu hỏi tự kiểm tra

**Câu 1:** `new SimpleGrantedAuthority("ADMIN")` có sai cú pháp không?  
**Đáp án:** Không. Đây là authority hợp lệ, nhưng `hasRole("ADMIN")` mặc định đòi `ROLE_ADMIN`, nên không tự khớp `ADMIN`.

**Câu 2:** `SimpleGrantedAuthority("ROLE_ADMIN")` có vai trò khác `SimpleGrantedAuthority("invoices.approve")` ở cấp Java class không?  
**Đáp án:** Không. Cả hai cùng một lớp; ý nghĩa do chuỗi và rule ứng dụng quy định.

**Câu 3:** Một JWT có claim `scope=orders.read`; tại sao rule `hasAuthority("orders.read")` không khớp mặc định?  
**Đáp án:** Với JWT scope converter mặc định, authority thường là `SCOPE_orders.read`. Cần xem mapping thực tế rồi kiểm đúng định danh.

**Câu 4:** Hai object `SimpleGrantedAuthority("ROLE_USER")` có thể bằng nhau dù được tạo khác lúc không?  
**Đáp án:** Có; `equals` và `hashCode` dựa trên cùng chuỗi.

**Câu 5:** Có `documents.read` thì được xem mọi tài liệu?  
**Đáp án:** Không đương nhiên; quyền theo object có thể còn cần owner, tenant, trạng thái, chia sẻ hoặc policy riêng.

**Câu 6:** Tạo một `SimpleGrantedAuthority("ROLE_ADMIN")` trong controller đã biến request thành quản trị viên chưa?  
**Đáp án:** Chưa. Việc cấp quyền phải diễn ra qua luồng authentication/authority mapping được tin cậy và rule áp lên `Authentication` thích hợp.

## Tóm tắt

- **`GrantedAuthority`** là interface mô tả quyền; **`SimpleGrantedAuthority`** là implementation giữ **một chuỗi định danh**.
- `SimpleGrantedAuthority` **không tự thêm tiền tố**, không phân biệt role/permission/scope bằng Java type và không tự kiểm tra quyền.
- **`hasAuthority("X")`** kiểm authority `X` theo đúng tên; **`hasRole("ADMIN")`** mặc định kiểm `ROLE_ADMIN`; **scope JWT** mặc định thường thành `SCOPE_...`.
- Quyền chỉ có giá trị khi được tạo từ nguồn đáng tin, gắn vào `Authentication` phù hợp và được kiểm bằng policy đúng. Quyền chung không tự thay quyền trên từng tài nguyên.
- Thống nhất định danh giữa **nguồn quyền → mapper → Authentication → authorization rule** là điều kiện quan trọng để tránh 403 khó hiểu hoặc cấp nhầm đặc quyền.

## Tài liệu tham khảo

- [SimpleGrantedAuthority – Spring Security Javadoc](https://docs.spring.io/spring-security/site/docs/6.5.11/api/org/springframework/security/core/authority/SimpleGrantedAuthority.html)
- [GrantedAuthority – Spring Security Javadoc](https://docs.spring.io/spring-security/site/docs/6.5.11/api/org/springframework/security/core/GrantedAuthority.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Maven Central – spring-security-core](https://central.sonatype.com/artifact/org.springframework.security/spring-security-core/6.5.11)

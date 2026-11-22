# Thay đổi quyền, khóa tài khoản và thu hồi các phiên đã đăng nhập trong Spring Security Servlet

Trong một ứng dụng Spring Security Servlet, người dùng đăng nhập bằng form, hệ thống xác thực qua `AuthenticationManager`, rồi lưu một `SecurityContext` chứa `Authentication` vào `HttpSession`. Sau đó quản trị viên có thể **hạ quyền**, **khóa tài khoản**, **vô hiệu hóa người dùng**, **đổi mật khẩu** hoặc yêu cầu **đăng xuất khỏi tất cả thiết bị**.

Một câu hỏi bảo mật quan trọng xuất hiện: **nếu thông tin tài khoản trong cơ sở dữ liệu thay đổi, các phiên đã đăng nhập trước đó có tự động nhận thay đổi và mất quyền ngay không?**

**Không nên mặc định là có.** Authentication đã lưu trong session thường mang thông tin principal/authorities được tạo tại thời điểm đăng nhập. Spring Security không có một cơ chế toàn cục bảo đảm mọi session trên mọi máy chủ đều bị làm mới hoặc thu hồi chỉ vì một hàng trong database người dùng thay đổi.

Bài này giải thích ba lớp trách nhiệm cần kết hợp:

1. **Trạng thái tài khoản nguồn sự thật:** tài khoản có bị khóa, vô hiệu hóa, xóa, yêu cầu đặt lại mật khẩu, và các vai trò/quyền hiện hành là gì?
2. **Trạng thái xác thực đã lưu:** `SecurityContext`, principal và authorities nào hiện vẫn tồn tại trong từng HTTP session?
3. **Cơ chế thu hồi và tái đánh giá:** cách làm session cũ hết hiệu lực, làm mới/kiểm tra lại quyền trước khi dùng, và cách kiểm thử cả hệ thống phân tán.

Phạm vi là **Spring Security Servlet / Spring MVC**, thông dụng ở Spring Security 6.x, form login và server-side HTTP sessions. Mã minh họa sử dụng Java 17+, Spring Boot 3.x. Các phiên bản phải được đối chiếu API và chính sách hỗ trợ thực tế; ví dụ không tuyên bố phiên bản dùng làm mẫu là mới nhất.

## 1. SecurityContext trong session là một ảnh chụp trạng thái, không phải truy vấn database trực tiếp

Quy trình cơ bản:

```text
POST /login
    |
UsernamePasswordAuthenticationFilter
    |
AuthenticationManager -> AuthenticationProvider
    |
UserDetailsService đọc user / vai trò / trạng thái từ DB
    |
Authentication đã được xác minh
    |
SecurityContextHolder <- SecurityContext(Authentication)
    |
SecurityContextRepository.saveContext(...)
    |
HttpSession chứa context đã lưu
    |
GET /account ở một request khác có cùng session ID
    |
Repository load SecurityContext từ session
    |
AuthorizationFilter kiểm tra Authentication.getAuthorities()
```

Sau khi user đăng nhập thành công, `SecurityContextRepository` có thể lưu context vào session. Khi request kế tiếp dùng cùng session, framework có thể lấy lại Authentication cũ **mà không gọi lại `UserDetailsService.loadUserByUsername` hoặc provider kiểm tra mật khẩu**. Đây là điểm tạo ra khoảng cách giữa **trạng thái hiện tại của tài khoản** và **quyền đang được sử dụng trong session**.

Ví dụ:

```text
10:00: alice login -> Authentication có ROLE_ADMIN -> session S1
10:05: quản trị viên xóa ROLE_ADMIN của alice trong database
10:06: alice gửi GET /admin cùng session S1
       nếu không revalidate/revoke, Authentication trong S1 có thể
       vẫn chứa ROLE_ADMIN từ lúc 10:00.
```

**Không suy luận rằng `authorizeHttpRequests().hasRole("ADMIN")` tự đọc lại DB ở mỗi request.** Nó thường ra quyết định dựa vào authorities đang có trong SecurityContext của request hiện tại. Method security cũng thường sử dụng Authentication được cung cấp cho lần gọi, trừ khi ứng dụng chủ động có cơ chế tái đánh giá dữ liệu hiện hành.

### Những loại thay đổi ảnh hưởng đến session ra sao?

| Thay đổi ở nguồn user | Hành vi khi đăng nhập **mới** | Rủi ro với session **đã tồn tại** |
|---|---|---|
| Đổi roles/authorities | Lần login mới thường nhận bộ quyền mới | Session cũ có thể giữ authorities trước đó |
| `accountNonLocked=false` (khóa user) | Provider tương ứng thường từ chối login mới | Context cũ không tự biến mất nếu không có kiểm tra/thu hồi |
| `enabled=false` hoặc tài khoản bị xóa | Login mới thường bị từ chối/không tìm thấy user | Session cũ có thể còn principal nếu không revalidate |
| Đổi password hoặc đánh dấu credential bị lộ | Lần login mới phải dùng credential hiện hành | Session cũ có thể tiếp tục hoạt động; đổi password không tự là “logout everywhere” |
| Xóa user khỏi nhóm/tenant | Lần xác thực lại có thể nhận quyền mới | Request cũ có thể dùng quyền tenant cũ hoặc data cache |
| Reset MFA hoặc xác định tài khoản bị chiếm | Một flow xác thực mới có thể đòi MFA | Những session được tin cậy trước sự cố cần chính sách thu hồi riêng |

Không phải mọi hệ thống nhất thiết phải invalidation toàn bộ session khi **tăng quyền**; song phải tránh giữ dữ liệu quyền cũ không đúng và tránh tự cấp quyền mới cho session chưa đạt điều kiện xác thực nâng cao. Với **giảm quyền/khóa tài khoản** hoặc sự cố bảo mật, yêu cầu thu hồi thường cần chặt chẽ hơn.

## 2. Phân biệt ba việc: chặn đăng nhập mới, hạ quyền đang dùng, thu hồi session

Một hệ thống có thể làm đúng **một việc** mà bỏ sót hai việc còn lại:

- **Chặn login tương lai:** `DaoAuthenticationProvider` hoặc provider thích hợp kiểm tra trạng thái user; các thuộc tính như `UserDetails.isAccountNonLocked()`, `isEnabled()`, `isAccountNonExpired()` được xét trong flow tương ứng. Việc này **không tự gửi tín hiệu tới các session đã xác thực**.
- **Đánh giá quyền ở mỗi request:** authorization dùng authorities đang nằm trong Authentication hoặc một policy service lấy dữ liệu hiện hành. Nếu không làm mới context hoặc kiểm tra trạng thái bảo mật, session cũ có thể giữ quyền cũ.
- **Thu hồi phiên đã cấp:** vô hiệu hóa server session, đánh dấu expired, xóa bản ghi session trong store, tăng security version hoặc ép reauthentication trên request sau. Mỗi cách có độ trễ và phạm vi bảo đảm khác nhau.

**Đổi password, đổi role, khóa tài khoản và logout có thể kích hoạt các hành động chung, nhưng không có nghĩa một thao tác này thay thế tất cả thao tác còn lại.**

Phân biệt:

| Câu hỏi | Cơ chế cần có |
|---|---|
| User bị khóa có login mới được không? | Kiểm tra trạng thái trong authentication provider |
| Session cũ của user bị khóa có còn gọi API được không? | Revalidation, revocation hoặc kiểm tra trạng thái ở authorization |
| Session trên một server khác có bị thu hồi không? | Kho session/registry dùng chung hoặc cơ chế phân tán |
| Request đã nạp context trước khi bị khóa có bị dừng ngay không? | Kiểm soát đồng thời và recheck ở điểm thực thi nhạy cảm; không chỉ xóa session |
| Client không dùng server-side session mà dùng JWT thì sao? | Token revocation/short TTL/version/introspection phù hợp; xóa HttpSession không tác dụng với JWT độc lập |

## 3. Nguyên tắc cập nhật quyền và trạng thái tài khoản an toàn

Khi quản trị viên thay đổi quyền hoặc khóa tài khoản, một workflow vận hành nên xác định:

1. **Xác thực và phân quyền người thực hiện thay đổi.** Chỉ quản trị viên có quyền mới được sửa quyền, khóa user, reset credential hoặc thu hồi phiên. Ngay cả admin cũng cần giới hạn đối tượng/tenant được quản lý.
2. **Ghi thay đổi vào nguồn dữ liệu tin cậy.** Dùng transaction/optimistic locking/version khi cần, để không ghi đè thay đổi đồng thời.
3. **Cập nhật tín hiệu thu hồi.** Có thể tăng `securityVersion`/`sessionEpoch` của user, công bố sự kiện sau commit, xóa sessions theo principal hoặc một tổ hợp phương án.
4. **Bảo đảm policy trước request tiếp theo.** Session cũ phải bị từ chối hoặc xác thực lại trước khi dùng quyền đã bị thu hồi. Khi yêu cầu an toàn cao, không chấp nhận việc một số node dùng cache quá cũ.
5. **Ghi audit tối thiểu.** Ai đã thay đổi gì, tài khoản nào, khi nào, kết quả gì, correlation ID nào; không log raw session ID, password, token hoặc bí mật reset.
6. **Kiểm tra tác động ở cụm nhiều node.** Không coi session registry in-memory của một instance là danh sách phiên toàn hệ thống.

**Thứ tự cập nhật quan trọng.** Nếu bạn xóa session trước khi transaction cập nhật role commit, người dùng có thể đăng nhập lại bằng quyền cũ trong khoảng hở. Với những thao tác thu hồi rủi ro cao, cần xác định thời điểm tính là có hiệu lực, xử lý rollback và thiết kế để không phục hồi quyền cũ do một sự kiện đến muộn.

### Chính sách đề xuất theo độ nhạy

- **Giảm quyền hoặc rời nhóm:** hủy/revalidate session liên quan để không còn dùng authorities cũ. Với quyền tài chính hoặc hành chính nhạy cảm, áp dụng kiểm tra trạng thái/permission mới ở điểm thực hiện hành động.
- **Khóa/disable account:** chặn đăng nhập mới và thu hồi mọi server-side session đã biết; có thể kết hợp kiểm tra `isAccountNonLocked`/`isEnabled` ở mỗi request để bảo vệ khi session store bỏ sót hoặc có race.
- **Đổi mật khẩu do user chủ động:** xác định có giữ session hiện tại hay không và session khác có bị đăng xuất không. Sau sự cố nghi bị lộ mật khẩu, thường cần thu hồi rộng hơn.
- **Thay đổi MFA hoặc quyền nhạy cảm:** xem lại mức bảo đảm xác thực của session cũ, có thể yêu cầu step-up authentication thay vì chỉ thêm authority vào context cũ.
- **Xóa user hoặc rời tenant:** bảo đảm cả context, object-level policy và cache dữ liệu không còn cho phép truy cập trái quyền.

## 4. Cách 1: SessionRegistry và đánh dấu các phiên expired

Spring Security Servlet có interface `SessionRegistry` và implementation in-memory `SessionRegistryImpl` để hỗ trợ tính năng quản lý phiên đồng thời và theo dõi session đã đăng ký.

Những API quan trọng:

- `getAllPrincipals()`: danh sách principal đã được registry theo dõi.
- `getAllSessions(principal, includeExpiredSessions)`: danh sách thông tin session cho principal đó.
- `SessionInformation.expireNow()`: đánh dấu session đã hết hiệu lực **trong registry**.

Ví dụ **mảnh Java minh họa** trong một service đã có `SessionRegistry registry` và `String targetUsername`, với principal là `UserDetails`:

```java
for (Object principal : registry.getAllPrincipals()) {
    if (principal instanceof UserDetails user
            && user.getUsername().equals(targetUsername)) {
        for (SessionInformation info
                : registry.getAllSessions(principal, false)) {
            info.expireNow();
        }
    }
}
```

Cần các import `org.springframework.security.core.userdetails.UserDetails`, `org.springframework.security.core.session.SessionRegistry` và `SessionInformation`. Đoạn này **không tự là một class chạy độc lập**, và chiến lược tìm principal phải khớp cách ứng dụng định danh user (username có thể đổi, tenant ID có thể trùng, principal không nhất thiết implements UserDetails).

### expireNow không phải xóa session ngay lập tức

**`SessionInformation.expireNow()` chỉ cập nhật trạng thái phiên trong registry.** Với cơ chế concurrent session control được nối đúng, `ConcurrentSessionFilter` có thể phát hiện session hết hạn trong **một request tiếp theo**, gọi expired-session strategy và tiến hành logout/invalidate theo cấu hình. Nó không tự gửi yêu cầu từ xa tới trình duyệt để lập tức kết thúc một request đang chạy.

Để phương án này hoạt động đúng, cần:

- Các session quan tâm **đã được đăng ký vào registry**. Một ứng dụng không bật session tracking có thể không có danh sách phiên mong muốn.
- Cấu hình xử lý expired session được nối vào security filter chain.
- Xóa đăng ký/session lifecycle đúng cách (với `SessionRegistryImpl`, thường cần `HttpSessionEventPublisher` để theo dõi session destroy).
- Cơ chế quản lý/đồng bộ registry phù hợp nhiều instance nếu hệ thống chạy cluster.

**Không suy rằng chỉ khai báo một bean `SessionRegistryImpl` là toàn bộ session đã được quản lý và mọi request sẽ kiểm tra expiration.** Cần kiểm tra actual `SecurityFilterChain`, session management configuration và integration tests.

### Phiên in-memory trên nhiều node

Nếu một node A gọi `registry.getAllPrincipals()` trong registry chỉ tồn tại trong memory của A, danh sách không nhất thiết có session do node B tạo. Sử dụng shared session infrastructure hoặc cơ chế theo dõi phiên phân tán phù hợp; đừng cam kết “logout all devices” trên toàn hệ thống nếu dữ liệu về phiên chỉ có tại một node.

## 5. Cách 2: Spring Session và xóa phiên theo principal

Với hệ thống lưu HTTP sessions tập trung qua Spring Session (tùy cấu hình Redis/JDBC hoặc repository khác), có thể dùng khả năng lập chỉ mục principal nếu repository hỗ trợ.

Ví dụ ở mức API, dùng `FindByIndexNameSessionRepository`:

```java
// Đoạn minh họa trong service có repository Spring Session phù hợp.
FindByIndexNameSessionRepository<? extends Session> repository = sessions;
Map<String, ? extends Session> byUser =
    repository.findByPrincipalName(username);

for (String sessionId : byUser.keySet()) {
    repository.deleteById(sessionId);
}
```

Cần các import Spring Session `FindByIndexNameSessionRepository`, `Session`, `Map`. Biến `sessions` và `username` phải được inject/truyền vào service; đây **không phải một file Java độc lập**.

Ý nghĩa:

1. Truy vấn session IDs theo principal được index.
2. Xóa các session được tìm thấy trong store, khiến lần truy cập sau thường không còn context trong session đó.
3. Buộc client thực hiện một phiên xác thực mới khi truy cập tài nguyên bảo vệ.

**Điều kiện cần:** session repository hỗ trợ `findByPrincipalName`; index principal được cấu hình/tạo đúng theo cơ chế Spring Security/Spring Session; các ứng dụng/nodes thực sự chia sẻ cùng session store và namespace phù hợp. Không có index hoặc session được tạo ngoài cơ chế quản lý thì truy vấn có thể không tìm đủ.

### Xóa session cũng có ranh giới thời gian

Một request đã nạp Authentication từ session **trước khi session bị xóa** có thể vẫn đang thực thi trong memory. Việc delete session từ store không tự đảo ngược một transaction đang chạy và không lấy context ra khỏi mọi thread đang xử lý. Với hành động nhạy cảm, cần **tái đánh giá tại điểm thực thi** hoặc so sánh security version/trạng thái hiện hành trước khi commit nghiệp vụ.

Ngoài ra, các thao tác “liệt kê rồi xóa” không nhất thiết atomic với request tạo session mới. Nếu một user đang đăng nhập đúng lúc admin khóa tài khoản, flow xác thực cũng phải kiểm tra trạng thái hiện hành trước khi cấp phiên; với chính sách nghiêm ngặt cần phiên bản bảo mật/điều kiện transaction để tránh session lọt vào khoảng hở.

## 6. Cách 3: Revalidation tại request để loại bỏ context cũ

Một lựa chọn khác là giữ **nguồn sự thật** về trạng thái tài khoản/quyền và **kiểm tra lại khi request đến**. Với ứng dụng nhỏ, có thể nạp `UserDetails` mới rồi so sánh với Authentication trong context. Với quy mô lớn, một trường `securityVersion`/`permissionsVersion`/`sessionEpoch` có thể gọn và rõ hơn.

Ý tưởng:

```text
POST /login:
  user hiện hành version=12 -> principal/session ghi version=12

Admin khóa user hoặc đổi quyền:
  update database, version=13, locked=true

GET /account với session version=12:
  filter revalidation đọc current version=13
  -> mismatch / locked
  -> xóa SecurityContext hiện tại, invalidate session
  -> trả 401 / yêu cầu xác thực lại

POST /login lần nữa:
  provider đọc locked=true -> từ chối đăng nhập
```

**Lợi ích:** không phụ thuộc hoàn toàn vào một danh sách session ID; request với Authentication cũ bị từ chối khi đi qua điểm kiểm tra thích hợp.

**Đánh đổi:** truy cập database/cache thêm, nguy cơ dữ liệu stale, lỗi hạ tầng, tính nhất quán và race với request đang chạy. Cần xác định kiểm tra trên mọi request nhạy cảm hay chỉ khi version thay đổi, cache TTL bao lâu, và lỗi store phải **fail closed** ở những tài nguyên có yêu cầu bảo mật cao.

Không chỉ so sánh `getAuthorities()` trong mọi ứng dụng: một lần user đổi mật khẩu hoặc bị buộc đăng xuất có thể **không làm thay đổi role**, nên phải có tín hiệu phiên bị thu hồi như security version. Ngược lại, một lần thăng quyền có thể yêu cầu xác thực nâng cao; không tự nâng authorities trong session cũ chỉ vì DB đã thêm ROLE_ADMIN.

### Tại sao không chỉ đọc DB ở controller?

Nếu chỉ kiểm tra trạng thái trong một controller mà các URL khác không kiểm tra, user có thể truy cập endpoint còn sót. Với yêu cầu toàn ứng dụng, đặt kiểm tra ở một điểm tập trung đáng tin như filter hoặc authorization manager; còn object-level authorization vẫn nên nằm gần service/data nghiệp vụ.

Một filter không tự bảo vệ code được gọi ngoài HTTP Servlet (jobs, messaging, gRPC). Hãy xác định mọi entry points có quyền nhạy cảm.

## 7. Ví dụ Spring Boot 3.x chạy được: tài khoản khóa/đổi quyền làm session cũ bị từ chối

Ví dụ này tập trung vào **hành vi kiểm chứng được**, không tự dựng một “admin endpoint” công khai để khóa hoặc nâng quyền user. Thay đổi trạng thái tài khoản được thực hiện **trong JUnit test** qua một store in-memory nhằm chứng minh lỗi stale session và biện pháp bảo vệ.

Công nghệ: Java 17+, Spring Boot **3.3.5** (mốc học tập, không phải bản mới nhất/được bảo đảm hỗ trợ), Spring Security 6 do Boot quản lý, Maven, MockMvc. Chúng ta giữ form login và HTTP session như một ứng dụng Servlet thông thường, thêm một `OncePerRequestFilter` đọc lại trạng thái user trước khi request đi tới authorization.

**Giới hạn minh bạch:** demo không triển khai phân tán, transaction hoặc hàng triệu users. So sánh authorities trực tiếp thích hợp để giải thích cơ chế; production nên có security version, session store/revocation service, caching policy và kiểm thử tải.

### 7.1. Cấu trúc thư mục

```text
session-revocation-demo/
├── pom.xml
└── src/
    ├── main/java/example/revocation/
    │   ├── RevocationApplication.java
    │   ├── DemoAccountState.java
    │   ├── AccountRevalidationFilter.java
    │   ├── SecurityConfiguration.java
    │   └── DemoController.java
    └── test/java/example/revocation/
        └── RevocationFlowTest.java
```

### 7.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>session-revocation-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. Entry point

Tạo `src/main/java/example/revocation/RevocationApplication.java`:

```java
package example.revocation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RevocationApplication {
    public static void main(String[] args) {
        SpringApplication.run(RevocationApplication.class, args);
    }
}
```

### 7.4. Store trạng thái minh họa

Tạo `src/main/java/example/revocation/DemoAccountState.java`:

```java
package example.revocation;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Component;

@Component
public class DemoAccountState {

    private final AtomicBoolean locked = new AtomicBoolean(false);
    private final AtomicReference<String> role =
        new AtomicReference<>("USER");

    public boolean isLocked() {
        return locked.get();
    }

    public String getRole() {
        return role.get();
    }

    public void setLocked(boolean value) {
        locked.set(value);
    }

    public void setRole(String value) {
        if (!value.equals("USER") && !value.equals("ADMIN")) {
            throw new IllegalArgumentException("Unsupported role");
        }
        role.set(value);
    }

    public void reset() {
        locked.set(false);
        role.set("USER");
    }
}
```

Store này chỉ có **một user demo** và giữ state trong memory. Nó không phải user repository production, không có audit/transaction/version; việc đọc lock và role từ hai atomic values cũng không tạo snapshot nhất quán giao dịch. Nó phục vụ việc quan sát thay đổi sau login trong MockMvc.

### 7.5. Filter tái đánh giá trước authorization

Tạo `src/main/java/example/revocation/AccountRevalidationFilter.java`:

```java
package example.revocation;

import java.io.IOException;
import java.util.HashSet;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.web.filter.OncePerRequestFilter;

public class AccountRevalidationFilter extends OncePerRequestFilter {

    private final UserDetailsService users;

    public AccountRevalidationFilter(UserDetailsService users) {
        this.users = users;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getServletPath();
        return path.equals("/public")
            || path.equals("/login")
            || path.equals("/logout")
            || path.equals("/error");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (authentication != null
                && authentication.isAuthenticated()
                && authentication.getPrincipal() instanceof UserDetails principal) {

            UserDetails fresh;
            try {
                fresh = users.loadUserByUsername(principal.getUsername());
            } catch (UsernameNotFoundException removedUser) {
                rejectAndInvalidate(request, response);
                return;
            }

            boolean blocked = !fresh.isEnabled()
                || !fresh.isAccountNonLocked()
                || !fresh.isAccountNonExpired()
                || !fresh.isCredentialsNonExpired();

            boolean rolesChanged = !new HashSet<>(fresh.getAuthorities())
                .equals(new HashSet<>(authentication.getAuthorities()));

            if (blocked || rolesChanged) {
                rejectAndInvalidate(request, response);
                return;
            }
        }

        chain.doFilter(request, response);
    }

    private void rejectAndInvalidate(
            HttpServletRequest request,
            HttpServletResponse response) {
        SecurityContextHolder.clearContext();
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
        // Demo cố ý trả 401 cho phiên đã bị thu hồi.
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
    }
}
```

Các quyết định quan trọng:

- Đặt filter **sau `SecurityContextHolderFilter`** để có thể lấy Authentication đã được repository nạp theo request, **trước bộ authorization** để trạng thái mới được áp dụng kịp thời. Đây là lựa chọn phù hợp với Security 6 trong ví dụ; cần đối chiếu filter order phiên bản thật khi mở rộng.
- Khi không có principal là `UserDetails`, filter không tự coi đó là account đã đăng nhập. `AnonymousAuthenticationToken` không bị nhầm với tài khoản thật vì principal thường không thuộc UserDetails; authorization bình thường tiếp tục xử lý.
- Khi DB biểu diễn tài khoản bị khóa/disabled/expired hoặc quyền đã đổi, filter xóa context trong request, invalidate HTTP session hiện tại rồi trả 401; request không tới controller.
- Trả 401 cho **phiên vừa bị thu hồi** là một hợp đồng response của demo; request ẩn danh bình thường vẫn có thể bị redirect tới login bởi form-login entry point.
- Không tự thay authorities trong session bằng quyền mới (đặc biệt khi **tăng quyền**) vì session có thể phải trải qua chính sách step-up/MFA. Buộc đăng nhập lại dễ giải thích hơn cho bài tập.
- Filter không bắt mọi `RuntimeException` và chuyển thành “tài khoản bị khóa”. Với production, lỗi store quyền phải có chiến lược fail closed/availability và metrics rõ ràng, không giấu sự cố.
- `OncePerRequestFilter` ngăn một số lời gọi lặp trong dispatch, không phải cơ chế thu hồi toàn bộ sessions hoặc chống retry từ hai HTTP requests khác nhau.

### 7.6. Cấu hình SecurityFilterChain và ngăn đăng ký Filter hai lần

Tạo `src/main/java/example/revocation/SecurityConfiguration.java`:

```java
package example.revocation;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.SecurityContextHolderFilter;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(DemoAccountState account, PasswordEncoder encoder) {
        String verifier = encoder.encode("demo-only-password");

        return username -> {
            if (!"alice".equals(username)) {
                throw new org.springframework.security.core.userdetails
                    .UsernameNotFoundException("Unknown user");
            }

            return User.withUsername("alice")
                .password(verifier)
                .accountLocked(account.isLocked())
                .authorities("ROLE_" + account.getRole())
                .build();
        };
    }

    @Bean
    AccountRevalidationFilter revalidationFilter(UserDetailsService users) {
        return new AccountRevalidationFilter(users);
    }

    @Bean
    FilterRegistrationBean<AccountRevalidationFilter> noContainerRegistration(
            AccountRevalidationFilter filter) {
        FilterRegistrationBean<AccountRevalidationFilter> registration =
            new FilterRegistrationBean<>(filter);
        registration.setEnabled(false);
        return registration;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AccountRevalidationFilter revalidation)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/error").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(form -> form
                .defaultSuccessUrl("/account", true)
                .failureUrl("/login?error")
                .permitAll())
            .addFilterAfter(revalidation, SecurityContextHolderFilter.class)
            .build();
    }
}
```

**Lưu ý về class ở trên:** để Java style dễ hiểu hơn, trong một file thực tế nên import `UsernameNotFoundException` rồi dùng tên ngắn trong lambda. Việc dùng tên class đầy đủ xuống dòng như minh họa cần đúng cú pháp Java; phiên bản toàn bộ chương trình để biên dịch có thể dùng cách sau, tương đương trong method `users(...)`:

```java
// Import ở đầu file:
import org.springframework.security.core.userdetails.UsernameNotFoundException;

// Trong lambda:
throw new UsernameNotFoundException("Unknown user");
```

Đoạn trên là chỉ dẫn thay thế cú pháp, **không chèn hai nhánh throw đồng thời**. Ví dụ đầy đủ về mặt hành vi khi sửa theo import gọn theo chỉ dẫn này. Các thành phần còn lại giữ nguyên.

**Vì sao cần `FilterRegistrationBean.setEnabled(false)`?** Vì filter do `@Bean` cung cấp là một Servlet `Filter`. Spring Boot có thể auto-register Filter bean vào container ngoài Spring Security chain. Đồng thời `addFilterAfter` đưa nó vào SecurityFilterChain. Vô hiệu container registration giúp tránh cùng filter chạy ở hai pipeline với thứ tự không mong muốn.

**Không cần tự lưu SecurityContext trong filter này.** Login chuẩn đã lưu Authentication qua repository phù hợp; filter revalidation chỉ dùng trạng thái session đã nạp, và **invalidate** session khi phát hiện lỗi thời.

Trong ví dụ `UserDetailsService` xây UserDetails từ store hiện hành khi authentication hoặc revalidation gọi đến; trong production, thay bằng database/service đã có transaction/permissionsVersion và xử lý errors phù hợp. Bật lại logger cực chi tiết cho raw credentials trong môi trường thật là rủi ro.

### 7.7. Controller

Tạo `src/main/java/example/revocation/DemoController.java`:

```java
package example.revocation;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage() {
        return "PUBLIC_OK";
    }

    @GetMapping("/account")
    public String account(Principal principal) {
        return "Hello, " + principal.getName();
    }

    @GetMapping("/admin")
    public String admin(Principal principal) {
        return "ADMIN_OK: " + principal.getName();
    }
}
```

Controller không có admin-mutation endpoint nào mở cho Internet. Trong test, store được đổi trực tiếp ở phía server để mô phỏng một thao tác quản trị đã được phân quyền và commit. Khi triển khai thật, bắt buộc thêm auditing/authorization/CSRF cho API sửa quyền hoặc khóa user.

### 7.8. MockMvc integration tests

Tạo `src/test/java/example/revocation/RevocationFlowTest.java`:

```java
package example.revocation;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RevocationFlowTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    DemoAccountState account;

    @BeforeEach
    void resetState() {
        account.reset();
    }

    MockHttpSession login() throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-only-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/account"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session).isNotNull();
        return session;
    }

    @Test
    void publicRouteWorksWithoutAuthentication() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC_OK"));
    }

    @Test
    void anonymousRequestRedirectsToLogin() throws Exception {
        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string("Location", containsString("/login")));
    }

    @Test
    void unchangedAccountKeepsItsSession() throws Exception {
        MockHttpSession session = login();

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello, alice"));
    }

    @Test
    void lockingAccountRevokesExistingSessionAndBlocksNewLogin()
            throws Exception {
        MockHttpSession session = login();
        account.setLocked(true);

        mvc.perform(get("/account").session(session))
            .andExpect(status().isUnauthorized());

        assertThat(session.isInvalid()).isTrue();

        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-only-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void roleDowngradeInvalidatesOldAdminSession() throws Exception {
        account.setRole("ADMIN");
        MockHttpSession oldSession = login();

        mvc.perform(get("/admin").session(oldSession))
            .andExpect(status().isOk())
            .andExpect(content().string("ADMIN_OK: alice"));

        account.setRole("USER");
        mvc.perform(get("/admin").session(oldSession))
            .andExpect(status().isUnauthorized());
        assertThat(oldSession.isInvalid()).isTrue();

        MockHttpSession newSession = login();
        mvc.perform(get("/admin").session(newSession))
            .andExpect(status().isForbidden());
    }

    @Test
    void roleUpgradeRequiresFreshAuthentication() throws Exception {
        MockHttpSession oldSession = login();
        account.setRole("ADMIN");

        mvc.perform(get("/admin").session(oldSession))
            .andExpect(status().isUnauthorized());
        assertThat(oldSession.isInvalid()).isTrue();

        MockHttpSession newSession = login();
        mvc.perform(get("/admin").session(newSession))
            .andExpect(status().isOk())
            .andExpect(content().string("ADMIN_OK: alice"));
    }

    @Test
    void loginPostWithoutCsrfTokenIsDenied() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "demo-only-password"))
            .andExpect(status().isForbidden());
    }
}
```

Các test bao phủ:

- Public endpoint khi anonymous.
- Protected endpoint chưa login.
- Session còn hợp lệ khi account không thay đổi.
- Account lock khiến session cũ bị từ chối ở request tiếp theo; `DaoAuthenticationProvider` từ chối login mới.
- Hạ quyền ADMIN xuống USER buộc session cũ hết hiệu lực; login mới còn user nhưng không có quyền ADMIN, trả 403.
- Nâng quyền cũng buộc xác thực lại; không tự cập nhật session cũ thành admin.
- CSRF protection vẫn hoạt động với POST login.

**Kỳ vọng:** bảy test thành công khi project được tạo đúng và sử dụng tương thích với Spring Boot 3.3.5/Java 17. Mã chưa được build hay chạy trong tài liệu này; các assertions mô tả hành vi cần xác minh trên máy thực tế. Test này không bảo đảm tất cả edge cases của session cluster hoặc race giữa nhiều HTTP requests.

### 7.9. Chạy thử

Từ thư mục chứa `pom.xml`:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

Trong demo chạy bằng server, chỉ có user thử nghiệm `alice / demo-only-password` được cấu hình. Không có public endpoint cho phép thay đổi trạng thái lock/role; các kịch bản biến đổi trạng thái được thực hiện trong JUnit test. Với session hợp lệ và user không bị khóa, `GET /account` tạo body chính xác:

```text
Hello, alice
```

Đừng sử dụng credential cố định hoặc store in-memory này làm thiết kế production. Nếu kiểm tra behavior trong trình duyệt, cần HTTPS và cookie policy phù hợp ở môi trường thật.

## 8. Biến demo thành thiết kế production: securityVersion / sessionEpoch

Với nhiều user, nhiều role và nhiều thiết bị, so sánh tất cả authorities ở mỗi request thường tốn kém và chưa bao phủ các sự kiện như password reset. Một thiết kế tốt hơn có thể dùng **monotonic security version** được quản lý ở nguồn dữ liệu tin cậy.

Ví dụ schema ý tưởng:

```text
users:
  id              UUID/long immutable
  account_status  ACTIVE / LOCKED / DISABLED
  security_version  BIGINT tăng dần theo mỗi sự kiện cần revoke
  updated_at       timestamp phục vụ audit, KHÔNG thay version đơn điệu

session authentication:
  immutable user_id
  security_version_at_login
  granted authorities snapshot
  authentication assurance / MFA level (nếu có)
```

Khi admin hạ quyền hoặc khóa tài khoản, transaction cập nhật user/role và tăng `security_version`. Ở request có session, filter hoặc AuthorizationManager kiểm tra:

```text
if account_status != ACTIVE -> revoke/deny
else if version_at_login != current_security_version -> revoke/reauthenticate
else -> cho phép đi tiếp tới authorization
```

**Không cần hash password hoặc gọi lại PasswordEncoder ở mỗi request.** Chỉ truy vấn user status/version theo immutable ID hoặc dùng cache có TTL/invalidations phù hợp; phiên bản được lưu trong principal/session phải là một giá trị trusted được gắn sau xác thực, không chấp nhận client tự khai báo version.

### Những bảo đảm cần thỏa thuận

- **Immediate revocation:** “Ngay” có thể hiểu là trước request kế tiếp, trước mọi hành động nhạy cảm, hay dừng cả request đang chạy. Ba mức này rất khác nhau.
- **Cache consistency:** cache TTL 60 giây có thể khiến user bị khóa vẫn được chấp nhận trong tối đa một khoảng trước khi đọc lại, nếu không có invalidation mạnh.
- **Fail closed:** nếu không đọc được trạng thái user do store lỗi, endpoint nguy hiểm có thể cần tạm từ chối thay vì tin vào snapshot cũ. Cần thông báo lỗi/availability riêng, không che mọi sự cố thành sai password.
- **Identity lifecycle:** không tái sử dụng username làm khóa bất biến nếu có rename/merge/tenant; dùng user ID và tenant ID ổn định.
- **Concurrent update:** tăng security version atomically cùng thay đổi cần revoke để tránh sự kiện mới ghi đè version cũ.
- **Cluster propagation:** phiên tạo ở node A phải bị kiểm tra/thu hồi nhất quán trên node B.
- **Request in flight:** kiểm tra version ở đầu request chưa đủ nếu thay quyền trong lúc request đang xử lý tác vụ dài. Với hành động chuyển tiền/cấp quyền, recheck tại điểm giao dịch hoặc dùng cơ chế đồng bộ thích hợp.

Nếu có yêu cầu “logout all devices” sau password compromise, ngoài server-side session còn phải xem xét remember-me tokens, refresh tokens, external IdP sessions, device tokens và bearer tokens khác. Xóa `HttpSession` chỉ xử lý đúng một loại credentials.

## 9. SessionRegistry, Spring Session và revalidation: chọn một hay kết hợp?

Một hệ thống đáng tin cậy có thể **kết hợp** để giảm độ trễ và tăng phạm vi phòng vệ:

| Biện pháp | Điều nó làm tốt | Giới hạn cần biết |
|---|---|---|
| `SessionRegistry.expireNow` | Đánh dấu phiên đang theo dõi là hết hiệu lực | Registry phải theo dõi session và có chain kiểm tra expired; không tự kết thúc request đang chạy |
| Spring Session `deleteById` theo principal | Xóa server sessions trong shared store | Cần chỉ mục principal, không tự dừng request đã nạp context, có race khi tạo session |
| Revalidation status/roles/version tại request | Từ chối session cũ trước authorization | Có chi phí đọc state và rủi ro stale cache/đứt kết nối |
| Per-action authorization từ nguồn dữ liệu hiện hành | Bảo vệ thao tác nhạy cảm đang thực thi | Cần thiết kế trong business layer và transaction |
| Session timeout và logout thông thường | Giới hạn thời gian sống, xử lý logout chủ động | Không đủ cho thu hồi khẩn cấp |
| Invalidate refresh tokens/remember-me | Ngăn credential khác cấp lại session | Cơ chế riêng; không tự xảy ra chỉ do HttpSession bị xóa |

**Lựa chọn:** ứng dụng nhỏ có thể bắt đầu bằng revalidation tại request cùng invalidation session, trong khi hệ thống nhiều node nên phối hợp shared session store và security version. Với nghiệp vụ nhạy cảm, luôn kiểm tra authorization tại action, không chỉ ngay sau đăng nhập.

## 10. Tại sao thay đổi quyền có thể gây lỗi khó thấy?

### 10.1. Cấp quyền ngay trên Authentication đã lưu

Một anti-pattern là quản trị viên cập nhật role của user trong DB, rồi một custom filter lấy role mới và **thay authorities của session hiện tại** mà không phân biệt tăng hay giảm quyền. Nếu user tăng từ `ROLE_USER` lên `ROLE_ADMIN`, phiên cũ có thể **chưa đạt yêu cầu MFA/step-up** cần cho vai trò mới. Ngược lại, nếu permission service có cache stale, mã đó còn có thể phục hồi quyền cũ.

**Chọn policy rõ:** invalidation + re-login/step-up, hoặc chính sách refresh authorities riêng được đánh giá. Không coi rehydrate Authentication là thao tác vô hại.

### 10.2. Khoá user chỉ tác động UserDetailsService

Cấu hình:

```java
User.withUsername(username)
    .password(encoded)
    .accountLocked(true)
    .build();
```

là một ví dụ thuộc **giai đoạn cung cấp UserDetails cho phép xác thực**, không phải lệnh xóa mọi SecurityContext cũ. Các session đang tồn tại phải được xử lý theo revocation policy.

### 10.3. Một server bị khóa, server khác chưa biết

Local `SessionRegistryImpl`, local cache user status hoặc in-memory blacklist có thể chỉ bảo vệ một node. Khi load balancer điều hướng request qua instance khác, quyền cũ vẫn được dùng. Cần shared repository/invalidation hoặc kiểm tra version từ kho chung.

### 10.4. Session vẫn hoạt động sau password reset

Nếu reset password không có policy revoke sessions, các session đã cấp bằng mật khẩu cũ vẫn có thể truy cập. **Đổi password không nhất thiết tự logout tất cả sessions**. Đặc biệt với nghi ngờ tài khoản bị chiếm, cần thu hồi cả remember-me/refresh tokens theo yêu cầu sản phẩm.

### 10.5. Request đang xử lý trước thời điểm khóa

Một API bắt đầu với session hợp lệ, sau đó admin khóa user trong lúc API thực hiện tác vụ dài. Xóa session không tự hủy transaction đã mở. Với hành động chuyển tiền, cập nhật quyền hoặc xuất dữ liệu, có thể cần recheck tài khoản/quyền tại điểm commit hoặc kiểm tra chống race có tính nhất quán đủ mạnh.

## 11. Lỗi thường gặp và chẩn đoán

| Hiện tượng | Điều cần kiểm tra | Phương pháp điều tra |
|---|---|---|
| User đã bị khóa vẫn vào trang admin được | SecurityContext cũ còn trong session; thiếu revocation/revalidation | So quyền trong context vs nguồn hiện hành, thử cùng session sau lock |
| Login mới bị chặn nhưng session cũ vẫn truy cập | Provider chỉ kiểm tra lock lúc login | Thêm chính sách thu hồi session hiện hữu hoặc per-request check |
| `expireNow` được gọi nhưng session chưa bị đá ngay | Chỉ đánh dấu expired; filter xử lý khi có request tiếp theo | Kiểm tra concurrent session filter, registry, expired-session strategy |
| Không tìm thấy session để revoke | Registry chưa đăng ký session hoặc principal index thiếu | Kiểm tra session tracking, principal representation, shared store |
| “Logout all” chỉ hoạt động trên node A | Registry/session chỉ local | Kiểm tra nhiều node, store chung, event propagation |
| Xóa session rồi user lập tức lại có session | Remember-me, refresh token, IdP login hoặc request đăng nhập đua | Kiểm tra tất cả credential issuers và thứ tự cập nhật status/revoke |
| Thay role nhưng trang vẫn hiển thị role cũ | Stale authorities/cached authorization hoặc UI cache | Phân biệt backend authorization với UI hiển thị, invalidate cache |
| Role tăng nhưng user không thấy quyền mới | Session đang giữ authorities cũ và policy yêu cầu re-login | Đây có thể là hành vi đúng của chính sách “step-up/reauthenticate” |
| User bị 401 đột ngột sau đổi role | Revalidation phát hiện version/authorities khác và thu hồi | Hiển thị thông điệp “Phiên không còn hợp lệ” và hướng dẫn đăng nhập lại |
| Test @WithMockUser pass nhưng session revoke lỗi | Mock authentication không đi qua login/session strategy thực | Kiểm thử POST /login, giữ session và thay nguồn user |
| Session bị invalidated nhưng API JWT còn dùng được | JWT là token độc lập với server session | Thiết kế revocation/expiry riêng cho token |
| Mọi request bị chậm vì đọc DB user | Revalidation truy vấn nặng hoặc gọi provider lại | Dùng security version/query nhỏ, cache có tính nhất quán phù hợp và benchmark |

**Không đo hiệu quả thu hồi chỉ bằng việc trang frontend thay đổi giao diện.** Phải gọi lại API bảo vệ với cookie/session **cũ**, kiểm tra status và quyền truy cập thực tế ở backend. UI có thể đang cache dữ liệu hoặc request không đi qua chain dự kiến.

## 12. Kiểm thử ở cấp độ integration và vận hành

Một bộ test có ý nghĩa nên xác minh cả **khả năng login mới** và **session đã tồn tại**.

Các trường hợp cần có:

1. User đăng nhập đúng; request kế tiếp dùng cùng session vẫn thành công.
2. User bị **khóa**; login mới bị chặn; session cũ không còn thực hiện được request bảo vệ.
3. User bị **disable/xóa**; session cũ bị chặn dù password chưa đổi.
4. **Hạ quyền** ADMIN → USER; session cũ không còn được quyền admin; login mới dùng quyền mới.
5. **Nâng quyền** USER → ADMIN; session cũ không được nâng im lặng nếu policy yêu cầu xác thực lại.
6. Đổi password hoặc tăng security version; session cũ bị thu hồi theo yêu cầu.
7. Hai browsers/thiết bị có cookie khác nhau; quyết định “logout all” áp dụng cho cả hai.
8. Multi-node: login tại A, đổi role tại B, dùng cookie cũ qua C; không được dựa vào shared memory giả.
9. Race: admin khóa user đồng thời request nhạy cảm bắt đầu hoặc lúc login mới tạo session.
10. Store lỗi/timeout: xác định endpoint nhạy cảm từ chối an toàn nhưng không tiết lộ thông tin hoặc tạo 500 khó chẩn đoán.
11. Logout, session timeout, remember-me, refresh token và SSO interaction hoạt động theo policy.
12. CSRF protection không bị tắt khi thêm API thay đổi role/lock hoặc khi viết filter mới.

Đặc biệt cần phân biệt **test data fixture** với session thật. Annotation `@WithMockUser` có ích cho authorization tests nhưng **không chứng minh** credential đã được provider xác minh, HTTP session đã lưu SecurityContext hoặc hệ thống đã thu hồi session. Với yêu cầu này, cần kiểm thử POST login qua filter chain và request kế tiếp mang cùng `MockHttpSession` hoặc cookie real container.

## 13. Checklist thiết kế “khóa account và logout all devices”

- [ ] Có nguồn trạng thái account/quyền nhất quán; khóa sử dụng immutable user ID và tenant ID.
- [ ] Đường **đăng nhập mới** từ chối user bị locked/disabled/deleted theo provider thực tế.
- [ ] Đường **session đã tồn tại** có cơ chế revoke hoặc revalidation, không tin mãi vào authorities snapshot.
- [ ] Hạ quyền và xóa quyền tenant được phản ánh trước khi request tiếp theo dùng quyền đã thu hồi.
- [ ] Nâng quyền có chính sách step-up/MFA hoặc yêu cầu re-login nếu nghiệp vụ cần.
- [ ] Có chỉ mục user→sessions hoặc session epoch/version để xử lý “logout all devices” đáng tin.
- [ ] Nếu dùng `SessionRegistry`, đã cấu hình đăng ký phiên và xử lý expired session, không chỉ gọi `expireNow`.
- [ ] Nếu dùng Spring Session, có repository/index chung và xử lý đa instance.
- [ ] Đã định nghĩa độ trễ tối đa có thể chấp nhận giữa thay đổi quyền và hiệu lực thu hồi.
- [ ] Có phương án chặn request đang xử lý nhạy cảm sau khi account bị khóa khi nghiệp vụ yêu cầu.
- [ ] Update role/lock và signal revocation có transaction/outbox hoặc cơ chế chịu lỗi đáng tin.
- [ ] Không còn remember-me/refresh token/JWT độc lập giúp client đăng nhập lại trái policy.
- [ ] Cấu hình HTTP session cookie/TLS, CSRF, session fixation và logout phù hợp.
- [ ] Không log raw password, cookie, session ID, access token, refresh token hoặc bí mật reset.
- [ ] Audit có thể giải thích ai khóa user, khi nào, bao nhiêu session đã được thu hồi và còn session nào không xử lý được.
- [ ] Kiểm thử trên **session cũ thực tế**, không chỉ database state hoặc UI.

### Câu hỏi tự kiểm tra

**1.** Spring Security đã nạp UserDetails lúc 09:00; lúc 10:00 admin bỏ `ROLE_ADMIN` trong DB. Session đã đăng nhập có tự mất role này ngay không?  
**Đáp án:** Không thể mặc định như vậy. Authentication trong session có thể giữ authorities cũ, cần cơ chế thu hồi hoặc tái đánh giá.

**2.** Chỉ đặt `accountNonLocked=false` có đủ để đăng xuất người dùng đang online không?  
**Đáp án:** Không. Thuộc tính đó được provider xem xét trong flow đăng nhập phù hợp; session đã tồn tại cần xử lý riêng.

**3.** Gọi `SessionInformation.expireNow()` có xóa cookie và ngắt mọi request đang chạy ngay tức thì không?  
**Đáp án:** Không. Nó đánh dấu registry; filter phù hợp thường xử lý ở request tiếp theo. Cookie và request đang xử lý có vòng đời riêng.

**4.** Dùng Spring Session `deleteById` cho mọi session ID tìm theo principal thì đã chặn mọi request in-flight chưa?  
**Đáp án:** Chưa. Request đã nạp context trước khi xóa có thể đang thực thi; cần policy/check tại action quan trọng.

**5.** Tại sao nâng quyền đôi khi cũng nên buộc login lại?  
**Đáp án:** Vì session cũ có thể chưa đáp ứng yêu cầu MFA/step-up hoặc độ tin cậy mới; không nên cấp quyền nhạy cảm bằng cách tự thay authorities.

**6.** Nếu API dùng bearer JWT mà không dùng HttpSession, xóa HttpSession có thu hồi JWT không?  
**Đáp án:** Không. Token tự mang trạng thái có cơ chế hết hạn/thu hồi riêng.

**7.** Test nào chứng minh đã bảo vệ đúng các session cũ?  
**Đáp án:** Đăng nhập để tạo session thật, thay đổi role/lock trên nguồn tin cậy, rồi gửi **request bảo vệ với chính session cũ** và xác minh 401/403 hoặc cơ chế từ chối đã thiết kế; đồng thời thử đăng nhập mới.

**Kết luận:** Trong Spring Security Servlet, **trạng thái account hiện tại, Authentication đã lưu trong HttpSession và chính sách revoke** là ba phần khác nhau. Đổi quyền hay khóa tài khoản không tự chắc chắn vô hiệu hóa các session đang hoạt động. Một thiết kế đúng cần **chặn login mới, thu hồi hoặc tái đánh giá session cũ, xử lý cluster và request in-flight, bảo vệ cả các credential ngoài HttpSession**, đồng thời kiểm thử sau khi thay đổi quyền — không chỉ trước khi đăng nhập.
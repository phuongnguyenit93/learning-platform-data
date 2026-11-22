# Thay đổi quyền lúc chạy và chính sách làm mới danh tính đã xác thực trong Spring Security Servlet

## 1. Bài toán: quyền đã thay đổi nhưng phiên đăng nhập vẫn dùng quyền cũ

Hãy tưởng tượng ứng dụng quản lý dự án đang sử dụng **Spring Security Servlet**. Lúc 09:00, tài khoản **learner** đăng nhập với authority **ROLE_USER**. Server xác thực mật khẩu, tạo một đối tượng **Authentication** và lưu nó trong **SecurityContext** gắn với **HttpSession**. Đến 09:05, quản trị viên cấp cho learner **ROLE_ADMIN** trong kho dữ liệu. Người dùng không đăng xuất, chỉ tải lại **/admin**.

Có chắc request lúc 09:06 sẽ có ROLE_ADMIN mới? **Không.** Nếu Spring Security lấy lại Authentication đã lưu trong session, đối tượng đó có thể vẫn chứa **snapshot ROLE_USER** tại thời điểm đăng nhập. Việc cập nhật cơ sở dữ liệu, UserDetailsManager hoặc bảng role **không tự động sửa mọi Authentication đã được phát ra**. Tình huống ngược lại còn nhạy cảm hơn: thu hồi ROLE_ADMIN ở kho dữ liệu nhưng phiên cũ vẫn giữ ROLE_ADMIN và có thể tiếp tục vượt qua các rule chỉ nhìn authorities cũ.

Đây là vấn đề **freshness của danh tính/quyền đã xác thực (authenticated identity and authorities)**, khác với việc xác thực mật khẩu ban đầu.

Bài học giúp bạn:

1. Phân biệt **trạng thái quyền nguồn** (database/identity service) với **Authentication snapshot** trong SecurityContext/session hoặc claims trong token.
2. Hiểu lúc nào Spring Security đọc lại **UserDetailsService**, lúc nào dùng Authentication đã lưu.
3. Đánh giá ba chính sách: **giữ snapshot đến hết phiên**, **làm mới quyền**, và **vô hiệu phiên rồi buộc đăng nhập lại**.
4. Triển khai một chính sách **rolesVersion**: tăng version khi quyền thay đổi, kiểm tra ở request kế tiếp và hủy session cũ trước khi tài nguyên nhạy cảm được xử lý.
5. Hiểu giới hạn của **SessionRegistry, Spring Session, JWT, OAuth2 Resource Server, bearer token, multi-node** và các request đang chạy.
6. Viết và thử một ứng dụng **Java 17+, Spring Boot 3.3.13, Spring Security 6**, sử dụng **form login + HttpSession + BCrypt + SecurityFilterChain**, với **MockMvc** chứng minh phiên cũ bị thu hồi khi quyền đổi.
7. Thiết kế kiểm thử **grant, revoke, disable account, stale session, fail-closed, cache TTL, race condition, object-level permission** và migration giữa các chính sách.

**Trọng tâm:** Mô hình phân quyền của **Spring Security Servlet**. Không coi đây là hướng dẫn xây hệ thống IAM/SSO hoàn chỉnh. Các ví dụ production cần điều chỉnh cho database, cluster, hệ thống cấp token và threat model thực tế.

## 2. Authentication là một kết quả xác thực tại một thời điểm

Trong Spring Security, **Authentication** thường biểu diễn:

- **principal**: danh tính đã xác minh (ví dụ UserDetails hoặc subject của JWT).
- **authorities**: các GrantedAuthority/role được xác nhận và sử dụng cho authorization.
- **credentials**: thông tin xác thực, thường được xóa/ẩn sau khi authentication thành công.
- **authenticated**: trạng thái mà provider xác nhận.
- **details**: metadata của request khi phù hợp.

Những thành phần liên quan:

| Thành phần | Nhiệm vụ | Quyền có tự cập nhật khi database đổi? |
| --- | --- | --- |
| **UserDetailsService** | Tải user và authorities từ nguồn dữ liệu | Chỉ khi được gọi lại |
| **AuthenticationProvider** | Xác minh credentials và xây Authentication | Trên lần xác thực đó |
| **AuthenticationManager** | Điều phối AuthenticationProvider | Không tự tìm mọi session cũ |
| **SecurityContextHolder** | Giữ SecurityContext của luồng/request hiện hành | Không tự đọc lại database |
| **SecurityContextRepository** | Nạp/lưu SecurityContext, có thể từ HttpSession | Lưu snapshot, không tự refresh |
| **AuthorizationFilter** | Đối chiếu request với Authentication và AuthorizationManager | Phụ thuộc authorities/policy được cung cấp |
| **Method security** | Áp dụng kiểm tra khi gọi method | Cũng cần policy và nguồn quyền đúng |
| **JWT decoder/resource server** | Xác minh token và tạo Authentication từ claims | Claims đã ký không tự thay đổi |
| **SessionRegistry/Spring Session** | Theo dõi/tìm session nếu cấu hình phù hợp | Có thể hỗ trợ thu hồi, không tự đồng bộ quyền |

Một rule:

~~~java
.requestMatchers("/admin").hasRole("ADMIN")
~~~

chỉ đối chiếu Authentication mà hệ thống đang sử dụng và authority **ROLE_ADMIN** theo convention mặc định. Rule đó **không tự truy vấn bảng roles mới nhất**. Đây là điểm cốt lõi khi tổ chức thay đổi quyền lúc runtime.

### SecurityContextHolder và HttpSession khác nhau

**SecurityContextHolder** cho phép code xử lý request truy cập security context hiện tại. Với ứng dụng Servlet dạng session, một **SecurityContextRepository** có thể nạp Authentication từ **HttpSession** ở request mới; không phải mỗi request luôn xác thực lại từ đầu.

Trong Spring Security 6, khi code tự tạo Authentication tùy chỉnh, cần hiểu cơ chế **explicit save**: đặt Authentication vào SecurityContextHolder **không đủ** để chắc chắn trạng thái được lưu cho request sau. Các filter đăng nhập chuẩn đã có quy trình riêng; code tự viết phải chọn repository và save đúng lúc. Bài thực hành dùng formLogin của framework để tránh tái triển khai toàn bộ lifecycle ấy.

### Snapshot không mặc nhiên là lỗi

Snapshot giúp tránh việc mỗi request luôn truy vấn database để lấy roles, giảm tải và cho độ trễ ổn định. Nhưng nó tạo **khoảng thời gian quyền có thể lỗi thời**. Cần chọn một chính sách nhất quán với yêu cầu bảo mật: độ trễ thu hồi quyền tối đa bao nhiêu, có chấp nhận buộc đăng nhập lại không, và những hành động quan trọng có cần kiểm tra policy mới nhất ngay tại thời điểm xử lý không.

## 3. Hai tình huống phải phân biệt: cấp quyền và thu hồi quyền

### 3.1. Cấp thêm quyền (grant)

~~~text
09:00  learner đăng nhập, Authentication có ROLE_USER
09:05  admin cấp ROLE_ADMIN trong nguồn dữ liệu
09:06  learner tải /admin bằng session cũ
~~~

Nếu sử dụng snapshot session không được làm mới, **/admin có thể vẫn bị 403** cho tới khi user đăng nhập lại, session được refresh hoặc authorization dựa vào chính sách live. Đây thường là vấn đề trải nghiệm người dùng: user mới được cấp quyền nhưng chưa dùng được.

Tuy nhiên, **không nhất thiết muốn tự cấp quyền cao hơn cho một session đã đăng nhập từ lâu**. Với hoạt động nhạy cảm, có thể yêu cầu xác thực lại mật khẩu, MFA/step-up hoặc confirmation trước khi dùng quyền mới. Việc tự refresh authority không phải lúc nào cũng là chính sách an toàn nhất.

### 3.2. Thu hồi quyền (revoke)

~~~text
09:00  admin đăng nhập, Authentication có ROLE_ADMIN
09:05  security team thu hồi ROLE_ADMIN
09:06  session cũ vẫn giữ Authentication chứa ROLE_ADMIN
09:07  request POST /admin/export-data
~~~

Nếu authorization chỉ dựa vào Authentication cũ, request có thể được chấp nhận dù database đã thu hồi quyền. Đây là rủi ro an toàn cao hơn trường hợp grant chậm.

**Đặc biệt:** thay đổi account status như **disabled/locked/deleted**, reset password, phát hiện session compromise hoặc thay đổi tenant cũng có thể cần thu hồi các Authentication hiện có, không chỉ thay role.

### 3.3. Có cần phản hồi ngay trong một request đang chạy?

Giả sử một request đã vượt qua check ROLE_ADMIN tại 09:04:59 và vẫn xử lý export trong 30 giây. Admin thu hồi quyền lúc 09:05:00. Một bộ lọc kiểm tra rolesVersion **ở đầu request** không thể quay ngược việc đã cấp quyền trước đó. Nếu nghiệp vụ yêu cầu thu hồi tức thời và nhất quán cao, cần kiểm tra quyền tại **thời điểm thao tác quan trọng**, hoặc thiết kế cơ chế hủy/đình chỉ công việc đang chạy và transaction/authorization phù hợp.

**“Hiệu lực ở request tiếp theo”** khác **“chặn ngay mọi tác vụ đang thực thi”**. Mức đảm bảo phải được định nghĩa rõ.

## 4. Quyền nguồn, quyền trong session và quyền trong JWT

Ba nguồn thông tin thường gặp:

~~~text
Database / IAM:
  learner -> [ROLE_USER, ROLE_ADMIN], rolesVersion=12
                      |
                authentication
                      |
          +-----------+------------+
          |                        |
   HttpSession snapshot       JWT claims snapshot
   roles=[ROLE_USER]          roles=[ROLE_USER]
   version=11                 iat=... / exp=...
          |                        |
      request mới             bearer token mới?
          |                        |
   context nạp từ session    parser tạo Authentication
          |                        |
   có thể vẫn version 11     token cũ vẫn claims cũ
~~~

**HttpSession:** tại login, một Authentication có authorities được lưu trong context. Đổi roles ở DB không ép context cũ tự cập nhật. Có thể invalidation hoặc refresh có kiểm soát.

**JWT tự chứa claims:** chữ ký hợp lệ chứng minh token do bên đáng tin cậy phát và chưa bị sửa theo những tiêu chí xác minh, **không chứng minh các role claims còn đúng với policy mới nhất**. Nếu token chưa hết hạn và resource server tin claims cũ, role cũ vẫn được sử dụng. Có thể giảm cửa sổ bằng token sống ngắn, revoke/introspection, kiểm tra version ở resource server hoặc không đặt quyền biến động mạnh trong token dài hạn.

**Opaque token + introspection:** resource server có thể hỏi authorization server token có còn active và có scope/roles gì, nhưng kết quả introspection cũng có thể được cache; cache TTL trở thành yếu tố freshness. Token revocation cũng phải được hệ thống thực thi đúng chỗ.

**HTTP Basic mỗi request:** nếu client gửi username/password mỗi request và provider tải user từ kho hiện tại, authority có thể phản ánh thay đổi ở lần xác thực tiếp theo. Nhưng user cache hoặc Authentication cache vẫn có thể làm chậm cập nhật; cũng không thể giả định mọi HTTP Basic client tự ngừng gửi credentials sau “logout”.

**SSO:** session của ứng dụng và session tại Identity Provider là hai thứ riêng. Hủy HttpSession app không có nghĩa SSO global logout hoặc revoke token ở IdP.

## 5. Ba chính sách phổ biến khi quyền thay đổi

| Chính sách | Cách hoạt động | Ưu điểm | Rủi ro/chi phí |
| --- | --- | --- | --- |
| **A — Snapshot đến hết phiên** | Session/JWT giữ authorities tại lần xác thực | Ít lookup, đơn giản | Revoke/grant có độ trễ dài |
| **B — Refresh Authentication** | Phát Authentication mới từ nguồn quyền đã xác minh | User có thể cập nhật quyền không logout | Phức tạp về session, race, step-up, principal integrity |
| **C — Invalidate và buộc xác thực lại** | Khi phát hiện version/quyền đổi, xóa session/context rồi yêu cầu login | Dễ lý giải, giảm nguy cơ role cũ tiếp tục được dùng | UX gián đoạn, phải phối hợp frontend/SSO |
| **D — Authorization động theo nguồn quyền** | Mỗi truy cập nhạy cảm hỏi policy/permission service | Revocation nhanh theo khả năng backend | Tăng độ trễ, cache/availability, phải dùng nhất quán mọi nơi |
| **E — Revoke token/session tập trung** | Chủ động vô hiệu các credentials liên quan khi có sự kiện | Kiểm soát tập trung multi-node | Cần registry/index, event/revocation infrastructure |

Không có một giải pháp tốt nhất cho mọi hệ thống. Có thể dùng kết hợp: **C/E** để thu hồi role nhạy cảm, **D** để bảo vệ thao tác quan trọng, **A** cho quyền ít nhạy cảm, **B** chỉ khi UX và điều kiện xác thực lại phù hợp.

### Quy tắc chọn dựa trên mức rủi ro

- **Permission có thể gây thiệt hại cao** (quản trị tài khoản, chuyển tiền, xuất dữ liệu nhạy cảm): không dựa hoàn toàn vào snapshot dài hạn; cần kiểm tra quyền mới nhất ở điểm thực hiện và cơ chế revoke.
- **Grant lên quyền cao:** cân nhắc yêu cầu reauthentication/MFA thay vì âm thầm nâng quyền trong session cũ.
- **Revoke quyền truy cập:** ưu tiên chính sách có thể chứng minh khoảng thời gian tối đa phiên cũ còn hiệu lực.
- **Quyền ít nhạy cảm:** có thể chấp nhận TTL hữu hạn và cập nhật tại lần login kế tiếp nếu được công bố rõ.
- **Nhiều node/region:** lưu version/registry ở nguồn chia sẻ, bảo đảm event delivery và cache invalidation chứ không chỉ Map trong một JVM.

## 6. Vì sao thay UserDetailsManager mà session vẫn “cũ”?

Xem ví dụ in-memory:

~~~java
// Fragment minh họa: users là InMemoryUserDetailsManager đã inject.
UserDetails old = users.loadUserByUsername("learner");
UserDetails updated = User.withUserDetails(old)
    .roles("ADMIN")
    .build();
users.updateUser(updated);
~~~

Thao tác **updateUser** thay đổi UserDetails trong kho user của JVM, nhưng nó **không duyệt các HttpSession đang tồn tại để sửa Authentication** đã lưu. UserDetailsService còn không phải nơi duy nhất Spring Security lấy danh tính khi request đến.

Ngược lại, nếu bạn đang dùng form login/session:

~~~text
POST /login -> UserDetailsService -> Authentication(ROLE_USER)
          -> SecurityContextRepository lưu Authentication vào session

GET /admin -> SecurityContextRepository nạp Authentication(ROLE_USER)
           -> hasRole("ADMIN") = false

Sau users.updateUser(... ROLE_ADMIN ...):
GET /admin -> Có thể vẫn nạp Authentication(ROLE_USER) cũ
~~~

Đừng sửa bằng cách gọi **SecurityContextHolder.getContext().getAuthentication().getAuthorities().add(...)**. Collection có thể bất biến, principal/Authentication đã được sử dụng nơi khác, và mutate ngay một object đang lưu trong session làm khó đảm bảo an toàn/đồng bộ. Nếu chủ đích refresh, hãy **tạo Authentication mới đã được xác minh, thay context theo lifecycle đúng, và lưu context vào repository** hoặc đơn giản hơn **invalidate và yêu cầu đăng nhập lại**.

### Không thể “ép mọi session” bằng SecurityContextHolder

SecurityContextHolder chỉ đại diện context hiện hành trong phạm vi xử lý. Nó không phải một database hay danh sách session của mọi người. Gọi SecurityContextHolder.clearContext() khi admin cập nhật role **chỉ xóa context của request hiện tại** (thường chính admin), không tự xóa phiên ở browser của learner.

Muốn xử lý phiên của user khác, cần một cơ chế biết **những session nào thuộc user đó**, có thể là SessionRegistry, Spring Session với index phù hợp, version check ở request, hoặc revocation service.

## 7. Mô hình rolesVersion: một cách kiểm tra độ mới

Một thiết kế phổ biến là lưu **version của thông tin quyền** trên nguồn dữ liệu và **version gắn với phiên lúc xác thực**.

~~~text
UserRoleRecord
  username = "learner"
  authorities = [ROLE_USER]
  rolesVersion = 7

HttpSession của learner
  SecurityContext = Authentication(ROLE_USER)
  AUTH_ROLES_VERSION = 7
~~~

Khi admin thay đổi roles, cập nhật có tính nhất quán theo chính sách:

~~~text
UserRoleRecord
  username = "learner"
  authorities = [ROLE_ADMIN]
  rolesVersion = 8

HttpSession cũ:
  AUTH_ROLES_VERSION = 7
~~~

Request kế tiếp:

~~~text
GET /admin với session cũ
   |
   v
Nạp Authentication từ SecurityContextRepository
   |
   v
Kiểm tra version 7 != version hiện tại 8
   |
   +-- invalidate session
   +-- clear SecurityContext
   +-- HTTP 401 / yêu cầu login lại
   |
   v
Không được vào endpoint admin với ROLE_USER/ROLE_ADMIN cũ
~~~

Khi login lại, provider tải UserDetails mới; session mới được gắn **rolesVersion=8** và Authentication có roles mới. Đây là chính sách **C — invalidate và reauthenticate**, không phải tự refresh authorities.

### Vì sao so version có ích hơn so cả danh sách roles?

- So một số version thường rẻ, ổn định hơn so tập authorities phức tạp.
- Có thể tăng version khi thay role, tenant membership, permission grants, account status hoặc policy có liên quan.
- Version có thể được lưu cùng user/tenant trong database và dùng cache ngắn hạn có kiểm soát.
- Khi làm multi-node, version chung giúp node khác phát hiện credential cũ ở request kế tiếp.

**Điều kiện:** version phải **tăng có kiểm soát** và đọc từ nguồn dữ liệu đáng tin. Nếu version lưu chỉ trong RAM của node A, node B không biết thay đổi; đây là giới hạn của demo và không đáp ứng thu hồi quyền toàn cluster.

### Lưu version ở đâu?

**HttpSession attribute** là lựa chọn đơn giản cho demo form login. Có thể lưu metadata trong custom principal hoặc một server-side session record. Không lấy version do client tự khai trong request header rồi tin đó là trạng thái mới nhất. Với JWT, version có thể nằm trong token nhưng cần so với version hiện tại ở một nguồn được tin tưởng để có ý nghĩa revoke.

## 8. Thiết kế demo: buộc đăng nhập lại khi quyền thay đổi

Ví dụ sử dụng:

- **Spring Boot 3.3.13 / Java 17+ / Maven**.
- **Spring Security Servlet**, form login mặc định, session cookie và CSRF mặc định.
- **InMemoryUserDetailsManager** seed một learner có ROLE_USER, BCrypt password.
- Một **RoleDirectory** cho test/admin-action mô phỏng đổi role và tăng rolesVersion.
- **RoleVersionFilter** được gắn vào SecurityFilterChain, kiểm tra version trước **AuthorizationFilter**.
- Nếu version sai hoặc session thiếu version cho một Authentication đã xác thực, filter hủy session, clear context, trả **401** để client login lại.
- Endpoint GET **/public**, GET **/me**, GET **/admin**; role change chỉ được gọi từ **test code**, không public REST API.

Chính sách ở đây cố ý thiên về an toàn: **không nâng hoặc giảm quyền trong Authentication đang sống**. Mọi session phát trước thời điểm role update sẽ cần xác thực lại ở request có Authentication tiếp theo. Phương án này giúp tránh sự nhập nhằng về bước nâng đặc quyền.

### Tại sao không làm endpoint POST /grant-role công khai?

Một API mà người dùng tự chọn username và ROLE_ADMIN để updateUser mà không có quản trị/authorization/audit là lỗ hổng nghiêm trọng. Để tập trung vào freshness, thay đổi role được thực hiện qua **RoleDirectory gọi trực tiếp trong integration test**, tương đương sự kiện admin đã được ủy quyền hoặc job IAM nội bộ. Production cần một workflow được kiểm soát, có log và permission riêng.

### Giới hạn cần ghi nhớ

Demo dùng **ConcurrentHashMap trong một JVM** để lưu version, không đồng bộ cluster, không có transaction bền vững. Kiểm tra version **ở đầu request** không hủy request đã qua authorization hoặc tránh mọi race giữa check và sử dụng dữ liệu. Production phải chọn source-of-truth/DB, event/revocation, atomicity và policy fail-closed theo yêu cầu.

## 9. Project Java 17+ hoàn chỉnh

### 9.1. Cây thư mục

~~~text
role-freshness-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/rolefreshness/
    │   ├── RoleFreshnessApplication.java
    │   ├── SecurityConfig.java
    │   ├── RoleDirectory.java
    │   ├── RoleVersionFilter.java
    │   └── DemoController.java
    └── test/java/com/example/rolefreshness/
        └── RoleFreshnessTest.java
~~~

### 9.2. pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>role-freshness-demo</artifactId>
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
~~~

Đây là một file Maven hoàn chỉnh, không cần ghép thêm XML. Dùng Spring Boot parent để quản lý phiên bản Spring Framework/Security cùng nhánh. Khi nâng cấp major version, các API filter/security có thể thay đổi: đối chiếu migration guide và chạy lại test.

### 9.3. RoleFreshnessApplication.java

~~~java
package com.example.rolefreshness;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RoleFreshnessApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoleFreshnessApplication.class, args);
    }
}
~~~

### 9.4. RoleDirectory.java — cập nhật user và version

~~~java
package com.example.rolefreshness;

import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.stereotype.Service;

@Service
public class RoleDirectory {

    private final InMemoryUserDetailsManager users;
    private final Map<String, Long> versions = new ConcurrentHashMap<>();

    public RoleDirectory(InMemoryUserDetailsManager users) {
        this.users = users;
    }

    // Chỉ minh họa kho version trong JVM, không phải nguồn multi-node.
    public synchronized long versionOf(String username) {
        return versions.computeIfAbsent(username, name -> 1L);
    }

    // Chỉ được gọi từ code quản trị đã được ủy quyền hoặc test.
    public synchronized void assignRole(String username, String role) {
        if (!Set.of("USER", "ADMIN").contains(role)) {
            throw new IllegalArgumentException("Unsupported role");
        }

        UserDetails previous = users.loadUserByUsername(username);

        UserDetails changed = User.withUserDetails(previous)
            .roles(role)
            .build();

        users.updateUser(changed);

        versions.merge(username, 1L, Long::sum);
    }
}
~~~

**Giải thích:**

- **InMemoryUserDetailsManager** lưu user/authorities trong JVM; demo không có database.
- **User.withUserDetails(previous)** giữ các thuộc tính account/password cũ và tạo UserDetails mới; **roles(role)** gắn authority ROLE_USER hoặc ROLE_ADMIN.
- **assignRole** chỉ nhận role từ allowlist, không nhận raw authority tùy ý từ client.
- Sau **updateUser**, version tăng 1. Những session đã gắn version cũ sẽ bị đánh dấu lỗi thời khi qua filter.
- **synchronized** chỉ giúp các lời gọi phương thức trong instance này có thứ tự rõ hơn; nó **không** cung cấp giao dịch database hoặc tính nguyên tử xuyên mọi filter/request/nhiều JVM.
- Một hệ thống thật cần cập nhật role/version cùng giao dịch thích hợp, hoặc cơ chế outbox/revocation nhất quán; xử lý event duplicate và các trường hợp update fail.

**Không có endpoint HTTP public cho assignRole**. Trong production, nghiệp vụ quản trị phải kiểm tra người thực hiện có quyền cấp/thu hồi quyền, MFA/step-up khi cần và audit mọi thay đổi.

### 9.5. RoleVersionFilter.java — chặn snapshot quyền cũ

~~~java
package com.example.rolefreshness;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class RoleVersionFilter extends OncePerRequestFilter {

    public static final String SESSION_VERSION =
        RoleVersionFilter.class.getName() + ".rolesVersion";

    private final RoleDirectory roles;

    public RoleVersionFilter(RoleDirectory roles) {
        this.roles = roles;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        if (auth != null && auth.isAuthenticated()
                && !(auth instanceof AnonymousAuthenticationToken)) {

            HttpSession session = request.getSession(false);
            Object atLogin = session == null
                ? null : session.getAttribute(SESSION_VERSION);

            long currentlyRequired = roles.versionOf(auth.getName());

            if (!(atLogin instanceof Long stored)
                    || stored.longValue() != currentlyRequired) {

                if (session != null) {
                    session.invalidate();
                }
                SecurityContextHolder.clearContext();

                response.setHeader("Cache-Control", "no-store");
                response.sendError(
                    HttpServletResponse.SC_UNAUTHORIZED,
                    "Authentication must be renewed");
                return;
            }
        }

        chain.doFilter(request, response);
    }
}
~~~

**Từng bước:**

1. Đây là **OncePerRequestFilter** trong **Servlet** stack. Nó không có @Component/@Bean riêng, nên Spring Boot không đăng ký nhầm như Servlet filter thứ hai; SecurityConfig gắn đúng một lần vào security chain.
2. Filter lấy Authentication hiện hành từ **SecurityContextHolder**, nơi chain đã nạp SecurityContext của session vào request.
3. Chỉ kiểm tra principal **đã xác thực**; request anonymous tiếp tục đến authorization bình thường.
4. Lấy HttpSession nếu đã tồn tại, **không** gọi getSession(true) để tạo session cho anonymous request.
5. Nếu session thiếu version hoặc khác với version hiện tại, filter **invalidate** và **clearContext**, trả 401 để yêu cầu một lần login mới. Thiếu version được xử lý **fail-closed** trong chính sách demo.
6. Nếu version bằng nhau, request đi tiếp tới **AuthorizationFilter** để kiểm tra roles của Authentication. Filter version không tự cấp quyền.
7. Response lỗi dùng **401** theo contract demo (không redirect). Điều đó khác entry point formLogin mặc định, nơi anonymous GET /admin có thể được redirect tới /login.

**Giới hạn kỹ thuật:** lọc trước AuthorizationFilter chỉ bảo vệ những request thật sự đi qua filter này, tại thời điểm nó được kiểm tra. Một request đã chạy qua filter có thể tiếp tục dùng snapshot; muốn bảo vệ thao tác dữ liệu nhạy cảm trước thay đổi đồng thời, phải áp kiểm tra mới nhất tại service/transaction.

**Không bắt mọi IOException/database outage thành “version bằng nhau”.** Nếu source-of-truth không đọc được, chính sách bảo mật cao cần fail-closed theo contract (ví dụ 503/401 tùy hệ thống) và có monitoring. Demo dùng in-memory lookup nên chưa minh họa outage phân tán.

### 9.6. SecurityConfig.java — formLogin và session version

~~~java
package com.example.rolefreshness;

import jakarta.servlet.http.HttpSession;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    InMemoryUserDetailsManager userDetailsService(
            PasswordEncoder encoder) {

        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("learn-pass"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            RoleDirectory roles) throws Exception {

        RoleVersionFilter versionFilter = new RoleVersionFilter(roles);

        http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login", "/error").permitAll()
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .successHandler((request, response, authentication) -> {
                    HttpSession session = request.getSession(true);

                    session.setAttribute(
                        RoleVersionFilter.SESSION_VERSION,
                        roles.versionOf(authentication.getName()));

                    // Demo dùng một redirect cố định thay SavedRequest.
                    response.sendRedirect(
                        request.getContextPath() + "/me");
                }))
            .addFilterBefore(versionFilter, AuthorizationFilter.class);

        return http.build();
    }
}
~~~

**Tại sao mã này dùng formLogin thay HTTP Basic?** Form login tạo một session chứa Authentication, nhờ đó dễ quan sát việc **authorities cũ sống qua nhiều request**. HTTP Basic thường xác thực lại từ raw credentials trên request mới và sẽ làm ví dụ “quyền snapshot ở session” khó minh họa.

**Tại sao lưu version trong successHandler?** Lúc xác thực thành công, provider đã tạo Authentication; success handler gắn version vào cùng HttpSession sử dụng để lưu SecurityContext. Những lần gọi tiếp theo có thể so với nguồn version của RoleDirectory.

**Tại sao addFilterBefore AuthorizationFilter?** Filter version phải kiểm tra **trước khi URL authorization được quyết định**. Nếu đặt sau AuthorizationFilter, một request với ROLE_ADMIN cũ có thể vượt qua check role trước khi đến bước phát hiện version lỗi thời.

**CSRF:** config không disable CSRF. POST /login cần token; integration tests dùng with(csrf()) và curl cần lấy token từ trang login. Demo chỉ có GET business endpoints, nên không cần thêm CSRF cho GET /me và GET /admin.

**Form login redirect:** successHandler tùy biến ở đây luôn redirect tới /me cho ngắn gọn. Nó không tự giữ cơ chế **SavedRequestAwareAuthenticationSuccessHandler** mặc định; khi tích hợp thật, nếu cần quay về URL mà người dùng truy cập trước login, hãy dùng handler chuẩn hoặc delegate phù hợp rồi gắn version trước khi delegate.

**Về login page:** GET /login do default login page của Spring Security cung cấp. Rule permitAll cho /login bảo đảm user anonymous đến được trang này. POST /login do UsernamePasswordAuthenticationFilter xử lý trước AuthorizationFilter, với CSRF bắt buộc theo mặc định.

**Về filter registration:** lớp RoleVersionFilter không có @Component và không được khai @Bean, vì nó được tạo và gắn trực tiếp trong SecurityFilterChain. Tránh đăng ký hai lần (Servlet filter + Spring Security filter) làm logic version chạy sai thứ tự.

## 10. Controller chỉ trình bày danh tính, không tự sửa role

Tạo file **src/main/java/com/example/rolefreshness/DemoController.java**:

~~~java
package com.example.rolefreshness;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public-ok");
    }

    @GetMapping("/me")
    public Map<String, Object> me(Authentication auth) {
        List<String> authorities = auth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "username", auth.getName(),
            "authorities", authorities);
    }

    @GetMapping("/admin")
    public Map<String, String> admin() {
        return Map.of("message", "admin-ok");
    }
}
~~~

Nếu GET /me với session còn hiệu lực, endpoint trả username và **authorities thuộc Authentication đã được kiểm tra version**, không trả password, session ID hoặc hash.

Lưu ý: controller trả danh sách authorities đã được dùng để authorize trong request, **không đại diện cho một API quản trị roles mới nhất tại mọi thời điểm**. Trong hệ thống thật, UI “tôi được cấp role gì?” có thể cần endpoint đọc nguồn user/permission hiện tại riêng, và policy sử dụng quyền cần thống nhất với nguồn đó.

## 11. MockMvc: chứng minh stale session bị thu hồi

Tạo file **src/test/java/com/example/rolefreshness/RoleFreshnessTest.java**:

~~~java
package com.example.rolefreshness;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class RoleFreshnessTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    RoleDirectory roles;

    private MockHttpSession loginLearner() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "learn-pass"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);

        assertNotNull(session);
        return session;
    }

    @Test
    void anonymousCanReadPublicEndpoint() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public-ok"));
    }

    @Test
    void learnerStartsWithRoleUser() throws Exception {
        MockHttpSession session = loginLearner();

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"))
            .andExpect(jsonPath("$.authorities[0]")
                .value("ROLE_USER"));

        mvc.perform(get("/admin").session(session))
            .andExpect(status().isForbidden());
    }

    @Test
    void grantAndRevokeRequireNewLogin() throws Exception {
        try {
            MockHttpSession first = loginLearner();

            mvc.perform(get("/admin").session(first))
                .andExpect(status().isForbidden());

            roles.assignRole("learner", "ADMIN");

            // Session cũ có ROLE_USER/version cũ: không được nâng quyền ngầm.
            mvc.perform(get("/admin").session(first))
                .andExpect(status().isUnauthorized());

            assertTrue(first.isInvalid());

            // Đăng nhập lại sẽ lấy ROLE_ADMIN từ user store đã đổi.
            MockHttpSession second = loginLearner();

            mvc.perform(get("/admin").session(second))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("admin-ok"));

            // Revoke quyền: session vừa có ROLE_ADMIN phải hết hiệu lực.
            roles.assignRole("learner", "USER");

            mvc.perform(get("/admin").session(second))
                .andExpect(status().isUnauthorized());

            assertTrue(second.isInvalid());

            MockHttpSession third = loginLearner();

            mvc.perform(get("/admin").session(third))
                .andExpect(status().isForbidden());

            mvc.perform(get("/me").session(third))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.authorities[0]")
                    .value("ROLE_USER"));

        } finally {
            // Dọn role để test khác không bị ảnh hưởng.
            roles.assignRole("learner", "USER");
        }
    }

    @Test
    void missingSessionVersionFailsClosed() throws Exception {
        MockHttpSession session = loginLearner();

        session.removeAttribute(RoleVersionFilter.SESSION_VERSION);

        mvc.perform(get("/me").session(session))
            .andExpect(status().isUnauthorized());

        assertTrue(session.isInvalid());
    }

    @Test
    void csrfIsRequiredForFormLogin() throws Exception {
        mvc.perform(post("/login")
                .param("username", "learner")
                .param("password", "learn-pass"))
            .andExpect(status().isForbidden());
    }
}
~~~

Thực thi:

~~~bash
mvn test
~~~

### Những bất biến được test

1. Anonymous GET /public vẫn công khai; filter không tạo session chỉ vì thấy request.
2. Khi mới login, learner có ROLE_USER; /admin bị 403 vì thiếu quyền, không phải sai mật khẩu.
3. **Grant ROLE_ADMIN** không tự biến session cũ thành session ADMIN: request tiếp theo bằng session cũ bị **401** và session bị invalidate.
4. **Login mới** nạp lại UserDetails sau grant nên /admin được phép.
5. **Revoke ROLE_ADMIN** làm session ADMIN cũ bị **401** khi request kế tiếp, trước khi dựa vào authority cũ; login mới chỉ có ROLE_USER.
6. Nếu một Authentication tồn tại nhưng thiếu attribute rolesVersion, chính sách demo fail-closed bằng cách hủy session và yêu cầu đăng nhập lại.
7. Form login dùng POST cần CSRF token; không tắt CSRF để test nhanh.

**Phân biệt rõ status:** 403 đầu tiên khi learner có session ROLE_USER hợp lệ là **authorization failure**. 401 sau khi version thay đổi là **chính sách bắt buộc renew Authentication của demo**. 401 ở đây do RoleVersionFilter trả, không phải phản hồi mặc định của form login khi anonymous truy cập /admin (trường hợp đó thường redirect tới /login).

### Vì sao test không dùng @WithMockUser?

@WithMockUser đưa một Authentication mô phỏng vào context của request test. Nó hữu ích cho authorization thuần túy, nhưng **không chứng minh flow login lưu Authentication trong HttpSession và rolesVersion**. Bài này dùng **POST /login với CSRF** rồi mang **MockHttpSession** sang request tiếp theo để quan sát chính sách freshness thật.

### Vì sao cần try/finally?

SpringBootTest có thể tái sử dụng ApplicationContext. RoleDirectory và InMemoryUserDetailsManager là singleton mutable state. Test gọi assignRole("learner","ADMIN") mà không khôi phục có thể làm test khác bị ảnh hưởng tùy thứ tự. **finally** bảo đảm role được trả về USER dù assertion thất bại; production nên thiết kế test fixtures/isolation rõ hơn và tránh chạy song song trên cùng username khi chưa có cơ chế khóa phù hợp.

### Giới hạn kiểm thử

MockMvc xác minh logic trong một ứng dụng JVM và test Servlet filter order, **không chứng minh** tính nhất quán của database nhiều node, event bus, token revocation, WebSocket đã mở hoặc những request đang xử lý đồng thời. Phần sau mô tả cách kiểm tra các tình huống đó khi mở rộng production.

## 12. Thử từ terminal với form login và CSRF

Chạy:

~~~bash
mvn spring-boot:run
~~~

Ứng dụng mặc định chạy ở **http://localhost:8080** nếu port khả dụng. Để login thủ công, mở:

~~~text
http://localhost:8080/login
~~~

Dùng tài khoản **learner / learn-pass**. Sau login, app redirect đến /me; JSON sẽ chứa ROLE_USER. GET /admin với cùng session bị 403.

Trong ứng dụng demo, không có **public admin API để thay đổi role**. Bước grant/revoke được thực hiện bằng lời gọi **RoleDirectory.assignRole(...) trong test**, tránh biến ví dụ thành endpoint tự cấp quyền. Để quan sát toàn bộ hành vi tự động, chạy **mvn test** theo mục 11.

Nếu muốn kiểm tra HTTP qua curl mà không viết UI riêng, cần nhận CSRF token hợp lệ cho cùng session. Login page mặc định của Spring Security có form chứa token ẩn **_csrf**. Có thể dùng browser DevTools/HTTP client hỗ trợ cookie và CSRF token để gửi POST /login; không nên gửi form login không CSRF rồi coi 403 là lỗi rolesVersion.

**Chỉ dùng HTTP localhost cho học tập.** Khi gửi credentials thật qua Internet phải dùng HTTPS và không hardcode password vào script/shell history. Authenticated identity phải được xác nhận ở server.

## 13. Ví dụ Java 17 thuần để hiểu version, không phụ thuộc Spring

Đây là một mô hình logic nhỏ, không thể thay thế authentication thật. Tạo file **RoleVersionTimeline.java**:

~~~java
public class RoleVersionTimeline {

    record Snapshot(String username, long rolesVersion) {}

    public static void main(String[] args) {
        long sourceVersion = 1L;
        Snapshot first = new Snapshot("learner", sourceVersion);

        System.out.println("initial: "
            + (first.rolesVersion() == sourceVersion));

        sourceVersion++;
        System.out.println("after-change: "
            + (first.rolesVersion() == sourceVersion));

        Snapshot second = new Snapshot("learner", sourceVersion);
        System.out.println("re-login: "
            + (second.rolesVersion() == sourceVersion));
    }
}
~~~

Biên dịch/chạy bằng JDK 17+ trong thư mục chứa file:

~~~bash
javac RoleVersionTimeline.java
java RoleVersionTimeline
~~~

**stdout chính xác:**

~~~text
initial: true
after-change: false
re-login: true
~~~

Giải thích: snapshot thứ nhất lưu version=1. Khi nguồn đổi sang 2, snapshot cũ không tự sửa; điều kiện version so sánh trở thành false. Snapshot được tạo lại sau khi “login lại” lưu version=2 nên đúng. Ví dụ này chỉ minh họa equality, **không** thực hiện authentication, session hoặc authorization và không nên được dùng như một thư viện bảo mật.

## 14. Nếu muốn refresh Authentication thay vì buộc đăng nhập lại?

Đó là một **chính sách khác** với demo. Khi quyết định refresh tự động, cần trả lời:

- **Nguồn authority nào đáng tin?** UserDetailsService, database, policy service hay IdP?
- **Principal nào đang được giữ?** UserDetails, OAuth2AuthenticationToken, JwtAuthenticationToken hoặc Authentication tùy biến?
- **Dữ liệu nào có thể thay đổi?** Authorities, tenant, account status, MFA/assurance level, authentication time?
- **Có cho phép nâng quyền không qua reauthentication?** Nếu user vừa được cấp ADMIN, hệ thống có yêu cầu MFA hay step-up không?
- **SecurityContext được lưu ở đâu?** HttpSessionSecurityContextRepository, request attribute, Spring Session?
- **Ai phát hiện thay đổi?** Event, version check, cache TTL, request lookup?
- **Khi nào lưu context?** Với Spring Security 6 và explicit save, phải lưu qua SecurityContextRepository nếu muốn request sau thấy Authentication mới.
- **Có nhiều request song song không?** Hai tab có thể lưu snapshot khác nhau; last-write-wins cần được xử lý.
- **Có session fixation hay CSRF token lifecycle không?** Việc đổi trạng thái authentication/privilege có thể cần áp dụng các session strategies liên quan.

Một fragment khái niệm:

~~~java
// Chỉ minh họa ý tưởng, KHÔNG phải code standalone.
// Authentication fresh = authenticationService.reauthenticateOrRefresh(...);
// SecurityContext updated = SecurityContextHolder.createEmptyContext();
// updated.setAuthentication(fresh);
// SecurityContextHolder.setContext(updated);
// repository.saveContext(updated, request, response);
~~~

**Đừng chỉ đổi collection authorities bằng Java reflection hoặc cast principal mutable.** Authentication mới phải được tạo từ nguồn đã kiểm chứng, có trạng thái account, assurance level, tenant, auth time và policy nhất quán. Dùng một số API khác nhau tùy loại Authentication và version Spring Security.

### Những trường hợp nên tránh refresh tự động

- Tài khoản vừa được cấp đặc quyền quản trị và chính sách yêu cầu MFA/reauthentication.
- Session đang có dấu hiệu bị đánh cắp.
- Account bị disabled/locked, không đơn thuần là thay danh sách role.
- Refresh context tự động sẽ bỏ qua yêu cầu user consent hoặc điều kiện cấp token mới.
- Ứng dụng không có khả năng bảo đảm đồng bộ context khi nhiều request ghi session đồng thời.

Trong những tình huống đó, **invalidate-and-reauth** thường dễ giải thích và kiểm thử hơn.

## 15. Authorization động: không lệ thuộc hoàn toàn vào role snapshot

Đối với quyền quản trị hoặc sở hữu tài nguyên, mô hình "user có ROLE_ADMIN lúc login" có thể quá thô. Ví dụ GET /projects/42 phải hỏi:

- Project 42 thuộc tenant nào?
- User hiện tại còn là thành viên của project không?
- Quyền đọc/ghi riêng của project đã bị thu hồi chưa?
- Có rule “chỉ owner được tải dữ liệu” không?
- Hệ thống có kiểm tra policy mới nhất sau role change không?

Một hướng thiết kế:

~~~text
Authentication -> userId được xác thực
       |
       v
Controller/Service yêu cầu hành động trên resourceId
       |
       v
PermissionService kiểm tra nguồn quyền hiện tại
       |
       +-- allowed -> xử lý nghiệp vụ
       |
       +-- denied  -> AccessDeniedException / 403
~~~

Spring Security có thể áp policy tại URL bằng **AuthorizationManager**, tại method bằng **@PreAuthorize** hoặc ở service bằng một thành phần kiểm tra quyền đã được xác minh. Với quyền phụ thuộc dữ liệu, kiểm tra ở **service/domain boundary** thường quan trọng vì URL matching không biết project thật sự thuộc ai.

**Ví dụ phân biệt:** RoleVersionFilter có thể bảo đảm session không dùng rolesVersion cũ từ thời điểm request bắt đầu. Nhưng nếu một project bị chuyển owner giữa lúc request chạy, một kiểm tra permission gần thao tác đọc/xuất dữ liệu vẫn cần thiết. Hai cơ chế giải quyết hai phạm vi khác nhau.

### Cache trong PermissionService

Cache permissions có thể giảm tải DB nhưng làm chậm revoke. Nếu cache TTL=60 giây, cần coi đó là một cửa sổ có thể lỗi thời; TTL chỉ là một yếu tố, còn event invalidation, replication lag và in-flight requests. Với hành động nhạy cảm, có thể giảm TTL hoặc đọc trực tiếp nguồn quyền trong transaction. Khi nguồn quyền không truy cập được, quyết định **fail-closed** phù hợp với risk.

## 16. Thu hồi session của user khác: SessionRegistry và Spring Session

Một admin thu hồi ROLE_ADMIN của learner muốn chấm dứt **mọi session** của learner, không chờ từng request gọi filter. Có các cơ chế hỗ trợ, nhưng phải biết giới hạn triển khai.

### 16.1. SessionRegistry trong Spring Security

**SessionRegistry** có thể theo dõi các principal/session và cung cấp SessionInformation. Có thể gọi **expireNow()** trên SessionInformation để đánh dấu session hết hạn. Nhưng:

- Cần cấu hình session tracking/concurrent session control thích hợp để registry biết những session cần quản lý.
- **expireNow()** là cơ chế đánh dấu; **ConcurrentSessionFilter** cần được tích hợp đúng để session được xử lý khi request kế tiếp đi qua chain.
- Registry chỉ giữ trong memory nếu dùng implementation in-memory; không tự giải quyết multi-node.
- Principal equality/key phải nhất quán; nếu principal thay đổi identity/equals, tìm session theo user có thể không như dự tính.
- Không suy ra mọi HttpSession đang tồn tại đều có trong SessionRegistry khi chưa test cấu hình thật.

Vì thế **SessionRegistry không phải một “global invalidateAllUsers()” tự xuất hiện** chỉ vì bạn inject bean. Cần setup và thử end-to-end.

### 16.2. Spring Session và session store chia sẻ

Với Redis/JDBC-backed Spring Session, có thể dùng repository có **index theo principal** để tìm session của user, rồi xóa các session nếu chính sách cho phép. Ví dụ khái niệm:

~~~text
Admin revokes role
  |
  v
Transaction cập nhật role/version trong DB
  |
  v
Session revocation service tìm session theo principalName
  |
  v
Xóa/đánh dấu hết hiệu lực trong store chia sẻ
  |
  v
Request trên node bất kỳ nạp session không còn hợp lệ
~~~

API và index cụ thể tùy loại Spring Session repository. Không giả định mọi backend có khả năng tìm tất cả session theo username, nhất là nếu chưa lưu principal index hoặc username có thể thay đổi.

### 16.3. Ưu và nhược của revoke chủ động

Ưu điểm là có thể loại nhiều session sớm, kể cả session không gửi request thường xuyên. Nhược điểm: cần quyền để enumerate sessions, bảo mật thao tác admin, xử lý event retries, session store availability và race với các session mới đang tạo. Một chính sách version-check ở request kết hợp revoke chủ động thường giúp có đường dự phòng nếu event delivery chậm, miễn nguồn version dùng chung.

## 17. JWT, access token và refresh token khi role thay đổi

Với bearer JWT, role thường nằm trong claims như roles/scope. Token được ký có thể còn hợp lệ **tới exp** dù quyền ở database đã thay đổi. Không thể sửa claims của một JWT đã phát mà vẫn giữ nguyên chữ ký.

Các chiến lược thực tế:

| Chiến lược | Tác dụng | Điều cần hiểu |
| --- | --- | --- |
| **Access token ngắn hạn** | Hạn chế thời gian quyền cũ còn trong token | Không thu hồi tức thời token đã phát |
| **Refresh token rotation và revocation** | Ngăn cấp access token mới từ refresh token bị thu hồi | Access token cũ có thể còn hiệu lực đến exp |
| **Token introspection** | Hỏi trạng thái token từ server | Cache/availability của introspection ảnh hưởng freshness |
| **Token denylist/jti** | Chặn token cụ thể bị revoke | Cần shared state và kiểm tra trên mỗi request liên quan |
| **rolesVersion/tokenVersion claim** | So version token với version hiện tại | Chỉ có hiệu lực nếu resource server thực hiện đối chiếu đáng tin |
| **Policy lookup mỗi action** | Không chỉ tin role claim cũ | Có chi phí và vấn đề dữ liệu/replication |

**Đừng viết:** “Chỉ cần cập nhật roles trong DB là JWT cũ bị thu hồi.” Chữ ký vẫn có thể hợp lệ, claims vẫn là snapshot cũ.

Nếu resource server có nhiều node và tự xác thực JWT offline, một event “role changed” gửi tới node A không nhất thiết khiến node B từ chối token. Cần chung nguồn version/denylist, introspection hoặc token sống ngắn theo risk.

### JWT đã bị thu hồi có thể còn ở cache không?

Có, tùy cách xác minh token. Một resource server có thể cache introspection/permission decisions. Khi thiết kế mục tiêu “revoke trong 5 giây”, cần tính cả cache TTL, replication, event delay, clock skew và request in flight. Một con số “access token exp trong 5 phút” không tương đương với “revoke mất 5 giây”.

### Đổi role có nên phát JWT mới ngay?

Không phải lúc nào cũng tự động. Nếu token mới có quyền cao hơn, cần đảm bảo user/session đáp ứng chính sách xác thực, ví dụ MFA. Phát token mới từ nguồn đúng và công bố rõ quy tắc nâng quyền. Khi revoke, ưu tiên không còn cho token cũ mang scope đã bị thu hồi vượt kiểm tra authorization.

## 18. Multi-node, cache và tính nhất quán

Demo dùng Map trong một JVM nên **không an toàn làm nguồn rolesVersion cho cluster**. Với hai node:

~~~text
Node A                     Node B
role change -> version=9   version cache vẫn=8
     |                         |
     v                         v
session tại A bị hủy      session tại B có thể vẫn qua check
~~~

Muốn thực thi chính sách thống nhất:

1. Lưu version trong **database/identity store được chia sẻ**.
2. Cập nhật quyền và version theo cơ chế transaction/atomicity phù hợp, tránh cửa sổ không nhất quán dài.
3. Nếu dùng cache, thiết kế **TTL, event invalidation, bounded staleness, fail-closed** cho endpoint nhạy cảm.
4. Dùng outbox/event bus nếu muốn chủ động revoke session ở nhiều node; xử lý event trùng và event đến trễ bằng version tăng đơn điệu.
5. Thực hiện xác thực/authorization ở đúng service xử lý nghiệp vụ, không chỉ tin gateway cache có quyền cũ.
6. Với request chạy lâu, dùng kiểm tra quyền ở **điểm commit/action** hoặc phương thức cancel khi cần.
7. Với WebSocket, SSE, background jobs, refresh trạng thái quyền của connection/job theo chính sách riêng: HTTP filter không tự kiểm tra lại từng message/job.
8. Đo độ trễ từ lúc admin bấm revoke tới lúc mọi node từ chối quyền cũ, không chỉ đo thời gian ghi DB.

### Race condition trong ví dụ

Ngay cả với RoleDirectory.assignRole(...) synchronized, một request có thể kiểm tra version trước khi thread khác đổi quyền, rồi tiếp tục AuthorizationFilter và thực hiện thao tác nhạy cảm sau thời điểm cập nhật. Bài demo **bảo đảm minh họa việc session bị hủy ở request kế tiếp sau khi role change đã hoàn tất**, không phải thu hồi có tính tuyến tính tuyệt đối trên mọi operation đồng thời.

Nếu nghiệp vụ cần “sau khi revoke transaction commit, không operation mới nào dùng quyền cũ”, cần thiết kế đồng bộ/transaction/serialization cụ thể tại ranh giới business operation; một servlet filter với version check ở đầu request **chưa đủ**.

### Khi nguồn version lỗi

Không nên bắt lỗi DB rồi mặc định coi roleVersion trùng. Với quyền nhạy cảm, khi không thể xác minh freshness, có thể từ chối bằng 503 hoặc mã thích hợp để **fail-closed**, đồng thời log/alert an toàn và có circuit breaker. Hãy ghi rõ chính sách này trong tài liệu SLA; một lỗi mạng không nên trở thành con đường bypass authorization.

## 19. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm hoặc sai | Cách xử lý |
| --- | --- | --- |
| Đổi UserDetails trong DB rồi nghĩ mọi session tự đổi | Authentication snapshot đã lưu | Version-check, invalidate hoặc refresh có kiểm soát |
| Dùng SecurityContextHolder.clearContext() ở request admin để xóa phiên user | Chỉ ảnh hưởng context hiện tại | Session registry/store hoặc check ở request của target |
| Mutate collection authorities trong session | Bất biến và thread safety không bảo đảm | Tạo Authentication mới hoặc revoke session |
| Chỉ kiểm tra hasRole("ADMIN") với JWT cũ | Role claim trong token có thể stale | Revocation/version/policy lookup |
| Thêm ROLE_ADMIN vào session cũ không step-up | Nâng quyền trong session thiếu assurance | Yêu cầu reauthentication/MFA theo policy |
| Xóa cookie nhưng session/token server vẫn hợp lệ | Cookie không phải credential revoke toàn diện | Invalidate server session/revoke token |
| Chỉ hủy một HttpSession khi có nhiều thiết bị | Phiên khác có thể vẫn còn | Per-user session enumeration/version |
| Dùng Map version in-memory trên cluster | Node khác không thấy thay đổi | Store chung, cache invalidation |
| Cache permissions quá lâu | Thu hồi bị chậm | SLO freshness, TTL ngắn, event invalidation |
| Bỏ qua CSRF khi sửa quyền | Browser có cookie tự gửi | CSRF protection cho unsafe methods |
| Test @WithMockUser rồi tin session refresh hoạt động | Mocked auth không mô phỏng login/session | MockMvc formLogin/real session tests |
| Không kiểm tra in-flight request | Filter chỉ chạy lúc request bắt đầu | Authorization ở điểm thực thi quan trọng |
| Bỏ qua WebSocket/job lâu dài | Không đi qua HTTP filter trên từng tác vụ | Lifecycle validation riêng |
| Thiếu fail-closed khi version store lỗi | Bypass do coi lỗi là “không đổi quyền” | Chọn policy an toàn và giám sát |
| Sai role prefix | roles("ADMIN") tạo ROLE_ADMIN | Đồng bộ hasRole/hasAuthority |
| Nghĩ STATUS 401 là 403 | 401 trong demo là renew auth; 403 là thiếu quyền | Ghi contract rõ ràng cho frontend |
| Auto-refresh quyền mới được cấp không kiểm tra session | Session cũ có thể bị đánh cắp | Step-up/reauth khi nâng đặc quyền |
| Không rollback role trong test | Shared Spring context bị mutate | try/finally hoặc fixture isolation |

### Quy trình debug

1. Xác định auth mechanism: form login/session, HTTP Basic, JWT, OAuth2/OIDC, remember-me hay custom.
2. Lấy authorities và metadata của **Authentication đang dùng** mà không ghi credentials bí mật.
3. Kiểm tra quyền nguồn hiện tại và roleVersion tại database/IAM.
4. Xác định request có nạp Authentication từ session/JWT hay xác thực lại từ UserDetailsService.
5. Kiểm tra filter/AuthorizationManager nào áp version/policy, và **vị trí trước AuthorizationFilter**.
6. Nếu revoke không có hiệu lực, kiểm tra version store, cache, session ID và nhiều node.
7. Nếu grant không hiện ra, phân biệt chính sách buộc re-login với lỗi data source.
8. Kiểm tra user/account status và tenant, không chỉ danh sách ROLE_.
9. Với 401, phân biệt expired credentials/session với thông báo phải đăng nhập lại; với 403 phân biệt thiếu quyền và CSRF.
10. Kiểm tra request đang chạy, background jobs và WebSocket nếu yêu cầu thu hồi tức thời.
11. Viết integration tests tái hiện trước khi thay đổi security config.
12. Không “sửa” bằng permitAll, disable CSRF hay bỏ authorization kiểm tra.

## 20. Bài tập thực hành và đáp án

### Bài A — Grant sau login

Learner đăng nhập với ROLE_USER, admin cấp ROLE_ADMIN trong database. Vì sao GET /admin qua HttpSession cũ có thể vẫn 403?

**Đáp án:** Authentication ở session có thể chứa snapshot ROLE_USER. Cập nhật database không tự refresh Authentication. Chính sách cần quy định refresh hoặc reauthenticate.

### Bài B — Revoke nguy hiểm hơn grant chậm

Admin đã login với ROLE_ADMIN; role bị thu hồi nhưng session vẫn có ROLE_ADMIN. Vì sao chỉ dùng hasRole("ADMIN") có thể chưa đủ?

**Đáp án:** Rule so với authority trong Authentication cũ, không tự kiểm tra version/quyền mới nhất. Cần revocation, version check hoặc policy lookup theo threat model.

### Bài C — Đổi role bằng UserDetailsManager

Gọi users.updateUser(updated) có tự duyệt mọi HttpSession của user để thay authorities không?

**Đáp án:** Không. UserDetailsManager cập nhật kho user, không tự cập nhật SecurityContext của các session đang sống.

### Bài D — Filter rolesVersion

Session lưu rolesVersion=4, kho dữ liệu hiện version=5. Trong policy demo, chuyện gì xảy ra ở request đã xác thực kế tiếp?

**Đáp án:** Filter phát hiện mismatch, invalidate session, clear SecurityContext, trả 401 để yêu cầu login lại. Nó không tự nâng quyền trong session cũ.

### Bài E — Tại sao phải đặt filter trước AuthorizationFilter?

Nếu RoleVersionFilter được gọi sau AuthorizationFilter, nguy cơ gì xuất hiện?

**Đáp án:** Role-based check có thể sử dụng authority cũ để cấp phép trước khi phát hiện version lỗi thời. Filter freshness phải được đặt đúng thứ tự trước quyết định authorization.

### Bài F — Quyền mới sau login lại

Nguồn dữ liệu đổi từ ROLE_USER sang ROLE_ADMIN và tăng version. Vì sao session mới có quyền ADMIN?

**Đáp án:** Khi login mới, AuthenticationProvider dùng UserDetailsService lấy UserDetails đã cập nhật. SuccessHandler gắn version hiện tại cho session mới.

### Bài G — JWT

JWT còn 30 phút hiệu lực và chứa ROLE_ADMIN. Role ở database đã bị thu hồi. JWT có tự thay đổi claims không?

**Đáp án:** Không. Token cũ có claims cố định; muốn revocation nhanh cần version/denylist/introspection, policy lookup hoặc cấu hình token lifetime phù hợp.

### Bài H — SessionRegistry

Chỉ tạo SessionRegistry bean, không cấu hình session tracking và ConcurrentSessionFilter. Có thể chắc chắn expireNow() thu hồi mọi HttpSession trên cluster không?

**Đáp án:** Không. Cần cấu hình integration đúng, session index/registry thực sự biết sessions, và backend chia sẻ nếu multi-node.

### Bài I — Race với request đang xử lý

Một request vượt qua RoleVersionFilter trước khi role bị thu hồi, sau đó hoàn thành hành động nhạy cảm. Filter có thể bảo đảm ngăn tuyệt đối không?

**Đáp án:** Không. Kiểm tra ở đầu request không thu hồi quyền của request in-flight. Cần authorization tại thời điểm operation/commit hoặc cơ chế cancel/serialization theo yêu cầu.

### Bài K — MFA khi grant ADMIN

Có nên tự động thay Authentication session bằng ROLE_ADMIN ngay khi admin cấp quyền mà không kiểm tra assurance level?

**Đáp án:** Không mặc định. Với đặc quyền cao nên xem xét reauthentication/MFA/step-up trước khi sử dụng role mới.

### Bài L — Fail-open hay fail-closed?

Nếu nguồn rolesVersion lỗi mạng, policy bảo vệ endpoint xuất dữ liệu nhạy cảm nên coi version trùng và cho phép không?

**Đáp án:** Không nên fail-open. Chọn cách từ chối an toàn, trả lỗi phù hợp và giám sát; chỉ cho phép khi đã chứng minh freshness theo policy.

### Bài M — Hai node

Node A tăng version trên Map cục bộ, node B vẫn đọc Map cũ. Tại sao request vào B có thể được chấp nhận?

**Đáp án:** Hai Map trong hai JVM không đồng bộ. Cần DB/session store/version source chung hoặc cơ chế invalidation chia sẻ.

## 21. Checklist triển khai production

- [ ] Đã xác định nguồn quyền đáng tin: database/IAM/policy service và owner của dữ liệu.
- [ ] Biết Authentication trong SecurityContext/session/JWT có thể là snapshot.
- [ ] Có chính sách riêng cho **grant**, **revoke**, **account disable** và thay tenant.
- [ ] Đã định nghĩa mức trễ revoke tối đa chấp nhận được cho từng loại hành động.
- [ ] Không tự xem việc đổi UserDetails ở nguồn dữ liệu là đồng nghĩa mọi phiên đã refresh.
- [ ] Không mutate authorities trong session; refresh phải tạo Authentication mới được xác minh.
- [ ] Với quyền nhạy cảm, cân nhắc invalidate-and-reauth/step-up thay vì silent privilege elevation.
- [ ] Khi dùng rolesVersion, version được cập nhật cùng role theo cơ chế tin cậy và so ở nguồn chung.
- [ ] Role freshness filter/policy chạy trước authorization hoặc gần business action phù hợp.
- [ ] Đã xử lý session thiếu version, lỗi source version và trạng thái account theo chính sách fail-closed.
- [ ] Có test session cũ sau grant, sau revoke và sau disabled-account event.
- [ ] Có test login lại lấy authorities mới, và session cũ thực sự không dùng lại được.
- [ ] Nếu có SessionRegistry/Spring Session, đã kiểm tra index và tính hiệu lực multi-node.
- [ ] Nếu dùng JWT/bearer, đã thiết kế token TTL, revocation và xử lý claims stale.
- [ ] Không chỉ dựa vào URL hasRole khi quyền phụ thuộc owner/tenant/resource.
- [ ] Không quên request đang chạy, WebSocket/SSE và background job.
- [ ] Cơ chế cache, event delivery và replication lag có SLO, giám sát và regression tests.
- [ ] CSRF, session fixation, cookie attributes, HTTPS và rate limiting vẫn được bảo đảm.
- [ ] Admin-role change API có authorization, audit, confirmation và MFA khi cần.
- [ ] Không log raw password, JWT, session cookie hay thông tin xác thực bí mật trong debug.
- [ ] Test thay đổi role có cleanup và không phụ thuộc thứ tự/parallel race.
- [ ] Người dùng/frontend hiểu contract 401 “phải đăng nhập lại” khác 403 “thiếu quyền”.
- [ ] Kiểm thử quyền đã thu hồi ở **tất cả** điểm thực hiện tác vụ nhạy cảm, không chỉ màn hình/UI.

**Kết luận:** Quyền tại database/IAM và authorities trong **Authentication đã lưu** không phải lúc nào cũng giống nhau. Khi quyền thay đổi lúc runtime, Spring Security Servlet **không tự động cập nhật toàn bộ HttpSession/JWT đang tồn tại**. Hãy chọn chính sách rõ ràng: chấp nhận snapshot có giới hạn, refresh Authentication an toàn, vô hiệu phiên rồi reauthenticate, hoặc kiểm tra permission mới nhất ở nơi dữ liệu được dùng. Ví dụ **rolesVersion + RoleVersionFilter** cho thấy cách **buộc session cũ hết hiệu lực ở request kế tiếp**, nhưng production cần giải quyết thêm transaction, multi-node, cache, token revocation và request in-flight nếu muốn đảm bảo thu hồi quyền mạnh hơn.

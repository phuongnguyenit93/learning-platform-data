# @WithUserDetails với UserDetailsService thực trong ngữ cảnh kiểm thử Spring Security Servlet

## 1. Vấn đề: kiểm thử method security bằng danh tính được tải từ ứng dụng

Khi một phương thức nghiệp vụ được bảo vệ bằng Spring Security, ta thường muốn kiểm tra rằng người dùng có quyền được gọi hàm còn người dùng thiếu quyền bị chặn. Ví dụ dịch vụ tạo báo cáo chỉ cho phép người có role ADMIN:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public String exportReport() {
    return "export-ok";
}
~~~

Đây là phương thức minh họa cần nằm trong một Spring-managed service và cần bật method security để annotation có tác dụng.

Một cách test nhanh là gắn **@WithMockUser(username = "alice", roles = "ADMIN")**. Nhưng annotation này tạo một người dùng **giả lập**, không gọi UserDetailsService của ứng dụng. Nếu production đang đọc role, trạng thái tài khoản hoặc thông tin người dùng từ database, một test với @WithMockUser có thể xanh dù logic tải người dùng thật đang hỏng.

**@WithUserDetails** được thiết kế cho nhu cầu khác: nó tìm bean **UserDetailsService** trong Spring ApplicationContext của bài test, gọi **loadUserByUsername** để lấy **UserDetails thực sự do bean đó trả về**, rồi đặt một Authentication phù hợp vào SecurityContext trước khi chạy test. Điều này giúp kiểm thử method authorization dựa trên authorities và principal do hệ thống tải, thay vì tự khai roles trong annotation test.

**Giới hạn cần hiểu:** @WithUserDetails không thực hiện đăng nhập HTTP, không gửi mật khẩu tới AuthenticationManager, không xác minh BCrypt và cũng không thực hiện OAuth/JWT token validation. Nó sử dụng UserDetailsService để **chuẩn bị security context cho test**. Vì vậy nó phù hợp với kiểm thử tích hợp tải principal và bảo vệ phương thức, không thay thế mọi bài test của luồng xác thực.

Bài áp dụng cho **Java 17+, Spring Boot 3.x, Spring Security 6.x, JUnit 5, Spring MVC/Servlet stack**. Trọng tâm là **kiểm thử phương thức** (method security), không phải chỉ kiểm tra status của một endpoint.

## 2. So sánh @WithMockUser và @WithUserDetails

| Tiêu chí | @WithMockUser | @WithUserDetails |
| --- | --- | --- |
| Nguồn UserDetails | Spring Security Test tự tạo principal giả lập | Gọi UserDetailsService bean trong ApplicationContext |
| UserDetailsService.loadUserByUsername | **Không gọi** | **Có gọi** |
| username | Định nghĩa trực tiếp trong annotation | Dùng để tra cứu người dùng qua service |
| authorities/roles | Khai báo trực tiếp trong annotation | Lấy từ UserDetails được service trả về |
| Cần user có trong repository | Không | Có, nếu UserDetailsService của bạn đọc repository |
| Cần ApplicationContext có bean UserDetailsService | Không bắt buộc chỉ để tạo mock user | Có |
| Kiểm tra password login thật | Không | Không |
| Phù hợp | Test một rule authorization đơn lẻ, nhanh | Integration test giữa user loader, authorities và method security |

Ví dụ test bằng mock user:

~~~java
@Test
@WithMockUser(username = "alice", roles = "ADMIN")
void adminCanExportUsingMockUser() {
    assertEquals("export-ok", reportService.exportReport());
}
~~~

Role ADMIN ở đây do test **tự gán**; không chứng minh UserDetailsService của ứng dụng thực sự trả ROLE_ADMIN cho Alice.

Ngược lại:

~~~java
@Test
@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "realUserDetailsService"
)
void adminCanExportUsingLoadedUser() {
    assertEquals("export-ok", reportService.exportReport());
}
~~~

Ở ví dụ thứ hai, Spring Security Test phải tìm được bean realUserDetailsService và load được username alice. Nếu service trả UserDetails không có ROLE_ADMIN, method sẽ bị từ chối dù test mong đợi thành công.

**Không gọi @WithUserDetails là kiểm thử đăng nhập thực.** Annotation tạo Authentication đã xác thực dựa vào UserDetails; nó **không** gửi password ở HTTP request và không kiểm tra mật khẩu input có khớp password hash hay không.

## 3. Điều kiện tiên quyết: bật method security và test đúng Spring bean

Spring Security 6 dùng **@EnableMethodSecurity** để bật các interceptor xử lý @PreAuthorize, @PostAuthorize và các expression method authorization có liên quan.

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Đây là một class cấu hình đầy đủ nếu thêm imports tương ứng và để Spring component scan phát hiện. Trong ứng dụng mẫu ở phần sau, annotation được đặt trong cấu hình bảo mật đang dùng.

Một method được bảo vệ:

~~~java
@Service
public class ReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public String exportReport() {
        return "export-ok";
    }
}
~~~

**Method phải được gọi qua Spring-managed proxy**. Nếu tự new ReportService() trong test, @PreAuthorize sẽ không có interceptor thực thi. Nếu một method trong cùng class tự gọi this.exportReport(), cơ chế proxy thông thường cũng có thể bị bỏ qua ở trường hợp self-invocation. Test muốn xác nhận method security phải **@Autowired service bean** rồi gọi từ bên ngoài bean.

Các điều kiện cần có:

1. Spring TestContext hoặc Spring Boot test dựng ApplicationContext có **UserDetailsService thực**.
2. Spring Security test listener được đăng ký (thường được Spring Test/Spring Boot tích hợp tự động khi có spring-security-test).
3. @EnableMethodSecurity có hiệu lực trong context.
4. Service được Spring tạo và được bọc proxy nếu cần.
5. UserDetailsService có thể tìm thấy user theo tên annotation cung cấp.
6. Cách lưu dữ liệu test phù hợp với thời điểm @WithUserDetails gọi loadUserByUsername.

Điểm cuối thường là lỗi khó nhất và sẽ được giải thích cụ thể ở phần 6.

## 4. @WithUserDetails hoạt động ở giai đoạn nào của test?

Một ví dụ:

~~~java
@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "realUserDetailsService"
)
~~~

Các thành phần:

- **value:** username cần truyền cho UserDetailsService.loadUserByUsername. Nếu bỏ qua, annotation dùng giá trị mặc định của nó (thường là "user"), không tự suy ra tên từ test method.
- **userDetailsServiceBeanName:** chỉ định tên bean UserDetailsService cụ thể, hữu ích khi context có nhiều bean hoặc cần chắc chắn gọi implementation đúng. Nếu có đúng một UserDetailsService, có thể bỏ thuộc tính này.
- **setupBefore:** chỉ định giai đoạn dựng SecurityContext: mặc định là **TestExecutionEvent.TEST_METHOD**; lựa chọn còn lại thường dùng là **TEST_EXECUTION**.

Spring Security Test dùng **WithSecurityContextTestExecutionListener** và factory tương ứng của @WithUserDetails. Khi đến giai đoạn setup, factory lấy bean UserDetailsService từ ApplicationContext, gọi loadUserByUsername, tạo Authentication dựa trên UserDetails được trả về và đặt vào SecurityContextHolder.

Luồng khái quát:

~~~text
JUnit / Spring TestContext
         |
         v
WithSecurityContextTestExecutionListener
         |
         v
@WithUserDetails annotation
         |
         +--> tìm UserDetailsService bean
         |
         +--> loadUserByUsername("alice")
         |      |
         |      +--> UserDetails với username, password, authorities...
         |
         +--> tạo authenticated Authentication
         |
         +--> đặt Authentication vào SecurityContext
         |
         v
test method gọi Spring-managed service
         |
         +--> @PreAuthorize kiểm tra authorities
         |
         +--> cho phép hoặc AccessDeniedException
~~~

Điểm rất quan trọng: **SecurityContext được dọn sau mỗi test** bởi test infrastructure để test này không làm bẩn test khác. Không nên tự giữ Authentication trong static field hoặc giả định context sẽ tồn tại mãi trong thread khác.

Các failure phổ biến trong bước setup:

- Tên bean không tồn tại -> test context/factory không chọn được UserDetailsService.
- loadUserByUsername trả lỗi UsernameNotFoundException -> test fail **trước khi chạy body test**.
- UserDetails được tải nhưng không có quyền mong đợi -> test chạy và @PreAuthorize từ chối.
- Repository/DB chưa có user ở thời điểm setup -> test fail sớm dù @BeforeEach dự định tạo user.

## 5. Phân biệt username, role, authority và principal thật

UserDetailsService chỉ có hợp đồng cốt lõi:

~~~java
UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
~~~

UserDetails chứa username, password (thường là hash), authorities và các thuộc tính trạng thái tài khoản. Việc sử dụng trực tiếp các thuộc tính tài khoản trong kiểm soát quyền phụ thuộc policy đã cấu hình.

Ví dụ loader trả:

~~~text
username: alice
password: {bcrypt}...
authorities:
  - ROLE_ADMIN
accountNonLocked: true
enabled: true
~~~

Khi @WithUserDetails dựng Authentication, principal thường là **UserDetails do service trả**. Đó có thể là org.springframework.security.core.userdetails.User hoặc class CustomUserDetails.

Đối với method:

~~~java
@PreAuthorize("hasRole('ADMIN')")
~~~

Spring Security dùng convention role prefix **ROLE_** ở cấu hình phổ biến. Nếu UserDetails có ROLE_ADMIN thì method được phép. Nếu chỉ có SCOPE_reports.read hoặc quyền "ADMIN" không có prefix khi dùng policy mặc định, kết quả có thể khác dự kiến.

Với @WithMockUser(roles="ADMIN"), mock test tự tạo ROLE_ADMIN. Với @WithUserDetails, authority phải xuất phát từ **service thực**. Đây chính là lợi ích khi muốn test mapping role từ DB.

**Cẩn trọng với trạng thái tài khoản:** @WithUserDetails không gọi toàn bộ AuthenticationProvider/PasswordEncoder để đăng nhập. Việc UserDetails có enabled=false hoặc accountLocked có thể không tự làm annotation thất bại theo đúng logic authentication thực tế. Nếu cần chứng minh tài khoản bị khóa không đăng nhập được, phải kiểm thử authentication pipeline riêng. Dùng @WithUserDetails để xác minh principal được tải và authorization, không để thay thế test của UserDetailsChecker.

## 6. Thứ tự @BeforeEach và setupBefore: chi tiết quyết định test có chạy không

Giả sử user alice được tạo trong database ở **@BeforeEach**:

~~~java
@BeforeEach
void seedUsers() {
    repository.save(new AppUser("alice", "...", "ADMIN"));
}
~~~

Nếu annotation test dùng setupBefore mặc định TEST_METHOD, SecurityContext thường được thiết lập trong giai đoạn **beforeTestMethod** của Spring TestContext, **trước** callback JUnit @BeforeEach. Khi đó loader gọi repository quá sớm; DB chưa có alice; test fail UsernameNotFoundException.

Để user được tạo **trước** khi @WithUserDetails tìm user, hãy dùng:

~~~java
@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "realUserDetailsService",
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
~~~

Với TEST_EXECUTION, SecurityContext được thiết lập vào giai đoạn **beforeTestExecution**, tức sau các callback JUnit @BeforeEach thông thường và ngay trước khi thực thi test method.

So sánh:

~~~text
setupBefore = TEST_METHOD (mặc định)

Spring beforeTestMethod:
  @WithUserDetails -> loadUserByUsername("alice")
JUnit @BeforeEach:
  seedUsers()
JUnit @Test:
  method security assertion

Nếu DB ban đầu trống: user được load QUÁ SỚM.


setupBefore = TEST_EXECUTION

Spring beforeTestMethod
JUnit @BeforeEach:
  seedUsers()
Spring beforeTestExecution:
  @WithUserDetails -> loadUserByUsername("alice")
JUnit @Test:
  method security assertion

User có trước khi loader chạy.
~~~

Lưu ý chi tiết lifecycle còn phụ thuộc TestExecutionListener, custom extensions và cấu hình transaction. Cách an toàn là đặt @BeforeEach rõ ràng, không dùng test-level @Transactional nếu không cần và kiểm chứng trạng thái DB đúng thời điểm load. Với repository-backed test bên dưới, các lệnh save của repository được thực thi/commit theo transaction của repository, vì test class không có @Transactional.

**Một giải pháp khác** là seed dữ liệu trước giai đoạn mặc định, ví dụ dùng @Sql với phase phù hợp, Testcontainers fixture hoặc dữ liệu khởi tạo ổn định. Nhưng @Sql BEFORE_TEST_METHOD và transaction của test cũng cần xét TestExecutionListener ordering. Khi fixture nằm trong @BeforeEach, sử dụng TEST_EXECUTION là lựa chọn trực tiếp và rõ ràng nhất.

## 7. Ví dụ tích hợp thực: UserDetailsService đọc JPA repository trong H2

Để tránh “test mock service giả” nhưng vẫn chạy độc lập, ứng dụng dưới đây dùng **Spring Data JPA + database H2 trong bộ nhớ**. UserDetailsService là bean service thực, thực hiện query repository. Method security vẫn chạy trên bean Service được Spring tạo.

### 7.1. Dependencies

Trong build.gradle (Groovy) của dự án đã có Spring Boot plugin/BOM tương thích, thêm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Ví dụ này test service trực tiếp, **không cần** spring-boot-starter-web hoặc MockMvc. Nó minh họa method authorization, không phải HTTP endpoint. Nếu ứng dụng thật có Spring MVC thì có thể giữ starter-web; cấu hình/filter khác có thể được kiểm thử riêng.

Giả sử package Java là **demo.withuserdetails**. Các file dưới đây cần nằm trong đúng package để Spring Boot component scan thấy repository, service, configuration và entity.

### 7.2. Lớp Spring Boot chính

File src/main/java/demo/withuserdetails/WithUserDetailsApplication.java:

~~~java
package demo.withuserdetails;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WithUserDetailsApplication {

    public static void main(String[] args) {
        SpringApplication.run(WithUserDetailsApplication.class, args);
    }
}
~~~

### 7.3. JPA entity đại diện user

File src/main/java/demo/withuserdetails/AppUser.java:

~~~java
package demo.withuserdetails;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "app_users")
public class AppUser {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String username;

    @Column(nullable = false)
    private String passwordHash;

    @Column(nullable = false)
    private String roleName;

    protected AppUser() {
        // Constructor phục vụ JPA.
    }

    public AppUser(String username,
                   String passwordHash,
                   String roleName) {
        this.username = username;
        this.passwordHash = passwordHash;
        this.roleName = roleName;
    }

    public String getUsername() {
        return username;
    }

    public String getPasswordHash() {
        return passwordHash;
    }

    public String getRoleName() {
        return roleName;
    }
}
~~~

RoleName trong demo lưu **ADMIN** hoặc **READER**, chưa có prefix ROLE_. Trong hệ thống thật, có thể tách entity role/permission theo quan hệ và kiểm tra authority mapping riêng. Ví dụ chỉ dùng một role cho mỗi user nhằm làm rõ cơ chế @WithUserDetails.

### 7.4. Repository thật

File src/main/java/demo/withuserdetails/AppUserRepository.java:

~~~java
package demo.withuserdetails;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface AppUserRepository extends JpaRepository<AppUser, Long> {

    Optional<AppUser> findByUsername(String username);
}
~~~

Đây là Spring Data repository thật: truy vấn findByUsername được triển khai dựa trên entity và database, không dùng Mockito. Trong integration test, H2 là database thật trong bộ nhớ và Hibernate tạo bảng theo JPA mappings.

### 7.5. UserDetailsService có tên bean xác định

File src/main/java/demo/withuserdetails/RealUserDetailsService.java:

~~~java
package demo.withuserdetails;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service("realUserDetailsService")
public class RealUserDetailsService implements UserDetailsService {

    private final AppUserRepository users;

    public RealUserDetailsService(AppUserRepository users) {
        this.users = users;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        AppUser appUser = users.findByUsername(username)
            .orElseThrow(() ->
                new UsernameNotFoundException(
                    "Unknown username: " + username
                )
            );

        return User.withUsername(appUser.getUsername())
            .password(appUser.getPasswordHash())
            .roles(appUser.getRoleName())
            .build();
    }
}
~~~

**@Service("realUserDetailsService")** vừa đăng ký bean thật vừa cho phép test chỉ định chính xác qua userDetailsServiceBeanName. Hàm gọi repository để lấy user. UserDetails được tạo bằng User builder, và roles("ADMIN") chuyển thành GrantedAuthority ROLE_ADMIN.

Nếu có nhiều bean UserDetailsService, khai rõ tên bean giúp không bị chọn nhầm. Đừng đặt cùng tên cho một bean mock trong test nếu mục tiêu là kiểm tra repository-backed implementation.

Không dùng passwordHash của user để so mật khẩu trong @WithUserDetails: annotation **không** chạy login password. Password hash có mặt vì UserDetails contract yêu cầu; việc kiểm tra password là trách nhiệm AuthenticationProvider trong test xác thực riêng.

### 7.6. Bật method security và password encoder

File src/main/java/demo/withuserdetails/SecurityConfig.java:

~~~java
package demo.withuserdetails;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
~~~

Với một ứng dụng service-level không có servlet web dependency, không cần SecurityFilterChain để gọi trực tiếp method security đã được kích hoạt. Ở một Spring MVC app thật, SecurityFilterChain còn xử lý authentication và authorization cho HTTP requests, tách khỏi việc kiểm thử service trực tiếp.

### 7.7. Service có phương thức bảo vệ bằng annotation

File src/main/java/demo/withuserdetails/ReportService.java:

~~~java
package demo.withuserdetails;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public String exportReport() {
        return "export-ok";
    }

    @PreAuthorize("hasAnyRole('ADMIN', 'READER')")
    public String readReport() {
        return "read-ok";
    }
}
~~~

Rule export chỉ cho ROLE_ADMIN; rule read cho ADMIN hoặc READER. Vì @EnableMethodSecurity đã bật, Spring sẽ dùng method security interceptor thông qua proxy cho lời gọi từ test tới Spring bean.

### 7.8. Test properties cho H2

File src/test/resources/application.properties:

~~~properties
spring.datasource.url=jdbc:h2:mem:security_method_test;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
~~~

Đây là database **riêng cho test**, không dùng cho dữ liệu production. Hibernate tạo schema lúc context dựng và loại bỏ khi context đóng theo ddl-auto create-drop. Trong nhiều ứng dụng thực tế, nên dùng migration scripts và test database tương tự production để kiểm tra schema/persistence phức tạp.

### 7.9. @SpringBootTest: tạo dữ liệu trước khi @WithUserDetails chạy

File src/test/java/demo/withuserdetails/ReportServiceIntegrationTest.java:

~~~java
package demo.withuserdetails;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.test.context.support.WithUserDetails;
import org.springframework.security.test.context.support.TestExecutionEvent;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class ReportServiceIntegrationTest {

    @Autowired
    AppUserRepository users;

    @Autowired
    PasswordEncoder encoder;

    @Autowired
    ReportService reports;

    @BeforeEach
    void seedDatabase() {
        users.deleteAll();

        users.saveAndFlush(new AppUser(
            "alice", encoder.encode("test-password"), "ADMIN"
        ));
        users.saveAndFlush(new AppUser(
            "bob", encoder.encode("test-password"), "READER"
        ));
    }

    @Test
    @WithUserDetails(
        value = "alice",
        userDetailsServiceBeanName = "realUserDetailsService",
        setupBefore = TestExecutionEvent.TEST_EXECUTION
    )
    void aliceIsLoadedFromDatabaseAndCanExport() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        assertTrue(authentication.getPrincipal() instanceof UserDetails);

        UserDetails loaded =
            (UserDetails) authentication.getPrincipal();

        assertEquals("alice", loaded.getUsername());
        assertTrue(
            loaded.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .anyMatch("ROLE_ADMIN"::equals)
        );

        assertEquals("export-ok", reports.exportReport());
        assertEquals("read-ok", reports.readReport());
    }

    @Test
    @WithUserDetails(
        value = "bob",
        userDetailsServiceBeanName = "realUserDetailsService",
        setupBefore = TestExecutionEvent.TEST_EXECUTION
    )
    void bobHasReadRoleButCannotExport() {
        assertEquals("read-ok", reports.readReport());

        assertThrows(
            AccessDeniedException.class,
            () -> reports.exportReport()
        );
    }
}
~~~

**Phân tích test theo đúng thứ tự:**

1. SpringBootTest nạp ApplicationContext đầy đủ, gồm JPA repository, RealUserDetailsService, ReportService và @EnableMethodSecurity.
2. JUnit @BeforeEach gọi users.deleteAll(), saveAndFlush cho alice và bob. Không có @Transactional ở test class, nên repository methods thực thi transaction riêng; dữ liệu đã sẵn sàng trước lúc TestExecutionEvent.TEST_EXECUTION.
3. Spring Security Test listener thấy @WithUserDetails của từng test, lấy bean tên realUserDetailsService và gọi loadUserByUsername("alice") hoặc ("bob") **sau @BeforeEach**.
4. RealUserDetailsService truy vấn AppUserRepository/H2 và tạo UserDetails với ROLE_ADMIN hoặc ROLE_READER.
5. Listener đặt Authentication đã xác thực vào SecurityContext; test có thể kiểm tra username và authorities.
6. reports là **Spring-managed bean**, nên lời gọi reports.exportReport() đi qua method security interceptor. Alice được phép; Bob bị AccessDeniedException.
7. Sau test, Spring Security test infrastructure dọn SecurityContext. @BeforeEach của test kế tiếp seed lại data, tránh phụ thuộc kết quả test trước.

Ví dụ không dùng @MockBean hoặc fake UserDetailsService. Đây là **integration test thực sự gọi UserDetailsService và repository**. Nhưng nó **không xác minh mật khẩu** vì @WithUserDetails không đi qua login HTTP hoặc PasswordEncoder.matches.

Để chạy (dự án có Gradle wrapper và dependency trên):

~~~bash
./gradlew test --tests demo.withuserdetails.ReportServiceIntegrationTest
~~~

Kết quả mong đợi là hai test pass với role mapping như mã; output dòng lệnh thực tế phụ thuộc công cụ build, database driver, Spring Boot version và môi trường. Không có stdout cố định vì đây là JUnit integration test, không phải chương trình println.

## 8. Chứng minh giá trị của UserDetailsService thật so với mock principal

Giả sử database thực tế lưu alice với role READER, nhưng một test viết:

~~~java
@WithMockUser(username = "alice", roles = "ADMIN")
~~~

Test đó vẫn tạo ROLE_ADMIN dù DB không chứa role ấy. Nếu dịch vụ có @PreAuthorize("hasRole('ADMIN')"), test có thể pass và tạo cảm giác mapping từ DB đúng trong khi production không cấp quyền như mong đợi.

Ngược lại:

~~~java
@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "realUserDetailsService",
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
~~~

sẽ lấy authorities từ RealUserDetailsService. Khi database đổi role của Alice thành READER, test kiểm tra ROLE_ADMIN hoặc exportReport phải fail, báo rằng kỳ vọng của test không khớp **dữ liệu thực được load**.

Đây là lý do nên dùng @WithUserDetails khi mục tiêu là integration giữa:

- repository/entity mapping;
- UserDetailsService;
- username lookup;
- authorities do service dựng;
- SecurityContext trong test;
- @PreAuthorize trên Spring-managed service.

Ngược lại, nếu chỉ kiểm tra rule “ROLE_ADMIN được phép, ROLE_READER bị chặn” và không cần DB, @WithMockUser thường nhanh và phù hợp hơn. Dùng hai loại test để cân bằng tốc độ với độ tin cậy, không mặc định annotation nào luôn tốt hơn.

## 9. UserDetailsService bean thật không nhất thiết đồng nghĩa production DB

Khái niệm **thật** ở đây là: @WithUserDetails gọi **bean UserDetailsService hiện diện trong test ApplicationContext** thay vì tự tạo mock UserDetails.

Bean đó có thể là:

- **JdbcUserDetailsManager** đọc bảng user/authorities trong H2, PostgreSQL hoặc database test khác.
- **Custom UserDetailsService** truy vấn JPA repository như ví dụ.
- **InMemoryUserDetailsManager** được đăng ký thật trong context để kiểm thử một policy nhất định.
- UserDetailsService gọi một service khác; môi trường test có thể dùng mock server để mô phỏng dependency bên ngoài nếu mục tiêu không phải test network.

Do đó phải xác định rõ lớp tích hợp cần kiểm tra. Một @WithUserDetails chạy với InMemoryUserDetailsManager vẫn gọi UserDetailsService thật, nhưng **không kiểm tra query của JPA repository**. Ngược lại, SpringBootTest + JPA repository/H2 cho phép xác minh đường load từ persistence tới UserDetails.

Không nên gọi test là “production-real authentication” chỉ vì có annotation @WithUserDetails. Nó **không** kiểm tra việc một người nhập mật khẩu sai có bị từ chối, JWT có đúng chữ ký, hay controller bảo vệ CORS/CSRF.

## 10. Các thuộc tính quan trọng của @WithUserDetails

### 10.1. value: username

Mặc định annotation có username mẫu, thường là user. Nếu môi trường test chỉ có alice, hãy khai tường minh:

~~~java
@WithUserDetails("alice")
~~~

Nếu không có user tương ứng, việc gọi UserDetailsService sẽ thất bại trong setup. Không dùng giá trị mặc định trừ khi dữ liệu test thực sự có username mặc định đó.

### 10.2. userDetailsServiceBeanName

Nếu context có nhiều UserDetailsService, chỉ định bean bằng tên:

~~~java
@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "realUserDetailsService"
)
~~~

Tên phải trùng tên bean trong ApplicationContext. Trong ví dụ, @Service("realUserDetailsService") tạo bean đúng tên. Nếu bean không tồn tại hoặc không phải UserDetailsService phù hợp, test không thiết lập được Authentication.

Không để một bean Mockito có cùng tên vô tình thay bean thật nếu mục tiêu là test quá trình tải user từ repository. Nếu trong một test khác bạn chủ động mock UserDetailsService, hãy ghi rõ scope là unit test, không gọi nó là integration test của loader thực.

### 10.3. setupBefore

~~~java
@WithUserDetails(
    value = "alice",
    setupBefore = TestExecutionEvent.TEST_EXECUTION
)
~~~

TEST_EXECUTION giúp fixture được tạo trong @BeforeEach trước khi loader truy cập DB. TEST_METHOD (mặc định) phù hợp khi user đã tồn tại từ trước khi JUnit @BeforeEach chạy. Sử dụng lifecycle chính xác đặc biệt quan trọng khi database test khởi đầu trống.

### 10.4. Class-level vs method-level

Có thể đặt @WithUserDetails ở class để mọi test sử dụng một danh tính mặc định, và đặt ở method để dùng user khác. Nhưng khi mỗi test seed DB trong @BeforeEach, cần kiểm soát setupBefore ở **annotation có hiệu lực** cho từng test. Đừng để class-level annotation tải user quá sớm trong khi method cần dữ liệu mới tạo.

### 10.5. Custom principal

Nếu UserDetailsService trả CustomUserDetails, test có thể kiểm tra principal thực có đúng kiểu và thuộc tính:

~~~java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

assertTrue(auth.getPrincipal() instanceof CustomUserDetails);
~~~

Đây là đoạn code minh họa, cần class CustomUserDetails và imports thích hợp. Không tự suy luận rằng principal của mọi authentication type đều là UserDetails; Resource Server JWT thường dùng JwtAuthenticationToken/Jwt và đòi test strategy khác.

## 11. Những lỗi phổ biến trong vòng đời và dữ liệu test

**Lỗi A — UsernameNotFoundException xuất hiện trước @BeforeEach.** Nguyên nhân thường là @WithUserDetails dùng TEST_METHOD mặc định trong khi user chỉ được tạo ở @BeforeEach. Dùng setupBefore=TEST_EXECUTION hoặc seed sớm hơn theo một quy trình đã kiểm chứng.

**Lỗi B — Không tìm thấy UserDetailsService bean.** Có thể đang dùng @WebMvcTest slice chỉ nạp MVC beans, không có service/repository. Dùng @SpringBootTest hoặc @Import cấu hình phù hợp với mục tiêu; nếu muốn test loader thật thì bảo đảm repository/data source cũng được nạp.

**Lỗi C — Có nhiều UserDetailsService.** Factory không biết chọn bean nào hoặc lấy sai bean. Dùng userDetailsServiceBeanName đúng và kiểm tra bean thực tế của test ApplicationContext.

**Lỗi D — @MockBean hoặc bean stub vô tình thay loader thật.** Test vẫn có thể pass nhưng không chạy repository query. Hãy xác định rõ integration scope và tránh mock đúng thành phần cần kiểm tra.

**Lỗi E — Dữ liệu test bị rollback hoặc chưa visible.** Với @Transactional trên test hoặc fixture, thứ tự transaction, repository save, flush và listener setup có thể gây khác biệt. Không giả định flush đồng nghĩa commit. Ví dụ bài dùng test không @Transactional để repository writes commit trước setup TEST_EXECUTION.

**Lỗi F — Gọi new ReportService().exportReport().** Bỏ qua Spring AOP proxy; @PreAuthorize có thể không chạy. Phải autowire Spring-managed bean. Cũng kiểm tra self-invocation nếu method nội bộ gọi method bảo vệ trong cùng object.

**Lỗi G — Chưa bật @EnableMethodSecurity.** Annotation @PreAuthorize có thể không có hiệu lực, test thiếu role vẫn chạy được. Đảm bảo cấu hình có annotation và test thực sự nạp nó.

**Lỗi H — Role prefix không khớp.** @PreAuthorize hasRole("ADMIN") thường đòi ROLE_ADMIN; nếu UserDetailsService trả authority ADMIN hoặc SCOPE_admin, policy có thể fail. Phân biệt roles(...) với authorities(...) và kiểm tra GrantedAuthority thực tế.

**Lỗi I — Nhầm @WithUserDetails với kiểm thử đăng nhập.** Không có request, không có PasswordEncoder.matches, không có authentication failure vì mật khẩu sai. Dùng MockMvc HTTP Basic/form login hoặc tích hợp provider thật cho test credential.

**Lỗi J — Context bị rò giữa các test.** Không tự giữ SecurityContextHolder trong static/global; để Spring Security Test dọn context và tạo lại theo từng test. Chú ý code async chạy khác thread không mặc nhiên có cùng context.

**Lỗi K — Test method bị disable hoặc class test không được runner nhận.** Cần JUnit 5, Spring test integration và spring-security-test dependency; @SpringBootTest của Boot cung cấp tích hợp SpringExtension trong cấu hình phổ biến.

**Lỗi L — Test dựa trên user của môi trường thật.** Không kết nối database production để tạo/sửa user từ integration test. Dùng test DB/schema/fixture và credentials không nhạy cảm; tránh rò password hash và thông tin khách hàng.

## 12. Vì sao method test trực tiếp thường tốt hơn MockMvc cho bài này?

Khi mục tiêu là @PreAuthorize trên ReportService và authorities do UserDetailsService tải, test trực tiếp Spring bean giúp chỉ rõ đường đi:

~~~text
Repository -> UserDetailsService
           -> @WithUserDetails -> SecurityContext
           -> method security proxy -> ReportService
~~~

Thêm MockMvc, DispatcherServlet, HTTP route hoặc CORS không làm nội dung kiểm tra permission của service chính xác hơn, trừ khi bạn muốn kiểm tra cả HTTP-layer authorization. Các endpoint web có thể có authentication filter, CSRF, servlet request matching, session, cookie hoặc JWT khác với test method.

Một hệ thống tốt có thể có:

- **Unit method tests với @WithMockUser:** chạy nhanh, test rule role/authority.
- **Integration method tests với @WithUserDetails:** tải authorities từ bean thật và test service proxy như ví dụ.
- **Authentication integration tests:** kiểm tra password hoặc token validation thực qua provider/filter.
- **HTTP end-to-end tests:** xác nhận SecurityFilterChain, status 401/403, CORS/CSRF, controller và nghiệp vụ.

Đừng ép toàn bộ những trách nhiệm trên vào một test duy nhất: test cồng kềnh sẽ khó xác định lỗi do phần nào.

## 13. Trường hợp dữ liệu test đã tồn tại từ trước

Nếu dữ liệu khởi tạo bằng SQL migration hoặc test fixture đã có sẵn trong database **trước lúc Spring Security Test listener setup**, có thể dùng mặc định:

~~~java
@Test
@WithUserDetails(
    value = "alice",
    userDetailsServiceBeanName = "realUserDetailsService"
)
void canLoadExistingUser() {
    assertEquals("export-ok", reports.exportReport());
}
~~~

Điều kiện: user alice phải tồn tại tại thời điểm listener chạy. Ví dụ, nếu setup database qua migration startup hoặc test fixture phù hợp, yêu cầu này có thể được đáp ứng.

Nhưng không chuyển tự động từ TEST_EXECUTION sang TEST_METHOD khi user vẫn được tạo trong @BeforeEach. Thứ tự lifecycle không thay đổi chỉ vì repository saveAndFlush được gọi trong BeforeEach; sự kiện TEST_METHOD đã diễn ra trước đó.

Nếu database còn dữ liệu từ test trước, một test setup sai có thể “tình cờ pass”. Tránh phụ thuộc thứ tự test: làm sạch/seed có kiểm soát, test độc lập và có cleanup theo test isolation strategy.

## 14. Tình huống mở rộng: test authorities từ dữ liệu thực

Để tăng giá trị integration test, không chỉ assert result của một method. Hãy chứng minh principal đã được load đúng:

~~~java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

UserDetails details = (UserDetails) auth.getPrincipal();

assertEquals("alice", details.getUsername());
assertTrue(details.getAuthorities().stream()
    .anyMatch(a -> a.getAuthority().equals("ROLE_ADMIN")));
~~~

Đây là đoạn code minh họa trong test có import Assertions, Authentication, SecurityContextHolder, UserDetails.

Nếu mapping JPA role sai hoặc UserDetailsService thiếu authority, assert sẽ fail. Nhờ vậy test phân biệt được lỗi **loader** với lỗi **method policy**. Ngược lại, nếu assert authorities pass nhưng method bị từ chối, kiểm tra @EnableMethodSecurity, proxying và expression.

Một số hệ thống còn có trạng thái enabled/locked, permission theo tổ chức hoặc role động. Chỉ đưa các thuộc tính đó vào integration test khi UserDetailsService thực sự trả và policy liên quan; nếu authorization cần truy vấn trạng thái tài nguyên ở service khác, phải test thêm lớp business authorization.

## 15. Câu hỏi thực hành và checklist

**Câu hỏi 1:** Test với @WithMockUser(roles="ADMIN") pass, nhưng user trong DB chỉ có READER. Điều này nói lên điều gì?

Nó chứng minh rule cho ROLE_ADMIN khi Authentication giả lập có quyền ấy; **không chứng minh** loader thật cấp ROLE_ADMIN. Sử dụng @WithUserDetails với UserDetailsService thật để kiểm tra mapping từ DB.

**Câu hỏi 2:** Tại sao annotation @WithUserDetails có thể báo không tìm thấy alice dù @BeforeEach có lệnh lưu alice?

Vì mặc định TEST_METHOD setup SecurityContext xảy ra trước JUnit @BeforeEach. Chọn TEST_EXECUTION để load sau seed.

**Câu hỏi 3:** @WithUserDetails có kiểm tra mật khẩu người dùng không?

Không. Nó gọi UserDetailsService để lấy principal và dựng Authentication cho test; muốn kiểm tra password phải qua authentication pipeline khác.

**Câu hỏi 4:** Tại sao phải @Autowired ReportService thay vì new ReportService?

Vì method security thường dùng Spring AOP interceptor/proxy. Gọi một object tự tạo sẽ bỏ qua proxy.

**Câu hỏi 5:** Khi có hai UserDetailsService bean, làm sao bảo đảm test dùng đúng service?

Chỉ định userDetailsServiceBeanName trùng tên bean mong muốn và kiểm tra ApplicationContext thực sự chứa implementation đó.

Checklist trước khi merge test:

- [ ] Có spring-security-test đúng phiên bản Spring Security, và Spring Test/JUnit 5 context được bật.
- [ ] Method security được bật bằng @EnableMethodSecurity.
- [ ] Test nạp **UserDetailsService bean thật** và repository/datasource cần thiết.
- [ ] Username trong @WithUserDetails tồn tại đúng thời điểm setup.
- [ ] Nếu seed trong @BeforeEach, dùng setupBefore=TEST_EXECUTION.
- [ ] Không mock chính UserDetailsService nếu mục tiêu là kiểm tra loader thực.
- [ ] Test gọi Spring-managed service proxy, không gọi new hoặc self-invocation.
- [ ] Kiểm tra principal/authorities đã được load, không chỉ kết quả method.
- [ ] Test cả user đủ quyền và user thiếu quyền.
- [ ] Không nhầm @WithUserDetails với test password login hoặc Bearer validation.
- [ ] Database test tách khỏi production, dữ liệu test độc lập theo từng case.
- [ ] Không log credential hoặc password hash để debug security context.

**Kết luận:** @WithUserDetails là công cụ dựng **SecurityContext từ UserDetailsService của ứng dụng** để kiểm thử method authorization. Khi dùng với repository thật và database test, nó phát hiện lỗi lookup/mapping authority mà @WithMockUser có thể bỏ qua. Thành công phụ thuộc vào context đúng, @EnableMethodSecurity, Spring proxy, username tồn tại và **thời điểm setupBefore**. Hãy hiểu rõ ranh giới của annotation: tải principal và kiểm tra quyền, **không thay thế quá trình xác thực mật khẩu hoặc access token thật**.

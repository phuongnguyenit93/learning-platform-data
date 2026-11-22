# Xóa credentials sau xác thực và tác động tới bộ nhớ đệm người dùng

## 1. Vấn đề thực tế

Trong ứng dụng **Spring Security trên Servlet stack**, một yêu cầu đăng nhập thường mang thông tin nhạy cảm như mật khẩu. Sau khi xác thực thành công, ứng dụng cần giữ **danh tính** và **quyền** của người dùng để xử lý request, nhưng thường **không cần giữ lại mật khẩu gốc** trong đối tượng Authentication. Spring Security có cơ chế chủ động xóa credentials khỏi kết quả xác thực nhằm giảm thời gian tồn tại của dữ liệu nhạy cảm trong bộ nhớ.

Điểm dễ bị bỏ qua: **đối tượng principal/UserDetails có thể được chia sẻ với một bộ nhớ đệm (user cache)**. Nếu việc xóa credentials làm thay đổi chính object đang lưu trong cache, bản cache có thể mất password hash cần cho lần xác thực tiếp theo. Khi đó request thứ nhất có thể đăng nhập bình thường, nhưng các request sau lại thất bại, phải truy vấn nguồn dữ liệu thêm lần nữa hoặc có hành vi không ổn định tùy cách cache được tổ chức.

Bài học này giúp bạn:

1. Xác định **ProviderManager**, **Authentication**, **CredentialsContainer** và cơ chế **eraseCredentialsAfterAuthentication** làm gì.
2. Phân biệt **mật khẩu do client gửi**, **password hash trong UserDetails**, **Authentication đã xác thực** và **UserCache/UserDetailsService cache**.
3. Hiểu vì sao xóa credentials là cần thiết, nhưng **không phải cam kết xóa an toàn mọi bản sao bí mật khỏi RAM**.
4. Nhận diện trường hợp **cùng một UserDetails object** được trả về từ cache rồi bị xóa password.
5. Chọn giải pháp ưu tiên: **giữ cơ chế xóa mặc định, không trả cùng instance mutable từ cache, sử dụng bản sao độc lập khi đưa user vào luồng xác thực**.
6. Tạo ví dụ Spring Boot Java 17+ có HTTP Basic, BCrypt, một user cache mô phỏng và kiểm thử hai lần xác thực liên tiếp.
7. Chẩn đoán hiện tượng login lần đầu được nhưng lần sau lỗi, đặc biệt khi bật cache trong môi trường nhiều request.

**Phạm vi:** Spring Security **Servlet** với xác thực username/password qua AuthenticationManager/DaoAuthenticationProvider. Các kiểu xác thực khác như bearer JWT, OAuth2/OIDC hoặc opaque token có mô hình credentials/principal riêng; không mặc định suy ra rằng mọi loại Authentication đều chứa và xóa password theo cách giống nhau.

## 2. Từ username/password tới Authentication đã xác thực

Luồng khái niệm cho form login hoặc HTTP Basic:

~~~text
HTTP request chứa username + password
       |
       v
Filter xác thực phù hợp
       |
       +--> tạo Authentication CHƯA xác thực
       |      principal = username
       |      credentials = password người dùng gửi
       |
       v
AuthenticationManager (thường là ProviderManager)
       |
       +--> AuthenticationProvider phù hợp
       |       |
       |       +--> UserDetailsService.loadUserByUsername(username)
       |       |        |
       |       |        +--> lấy user từ DB hoặc cache (có password hash)
       |       |
       |       +--> PasswordEncoder.matches(rawPassword, encodedPassword)
       |       +--> kiểm tra trạng thái account, authorities
       |
       +--> tạo kết quả Authentication ĐÃ xác thực
       |
       +--> xóa credentials khỏi kết quả, khi cấu hình mặc định áp dụng
       |
       v
SecurityContextHolder -> Authentication đã xác thực
       |
       v
AuthorizationFilter -> Controller / Service
~~~

**Authentication** mô tả kết quả xác thực hiện tại. Một Authentication có thể có principal là **UserDetails**, credentials là **String mật khẩu** hoặc đối tượng credentials khác, và collection các **GrantedAuthority**. Kết quả đã xác thực vẫn cần giữ principal và quyền; thông thường không cần giữ raw password để xử lý authorization.

**UserDetailsService** chỉ có nhiệm vụ **tìm thông tin user** theo username. Nó không tự xác thực HTTP request, không quyết định chính sách URL và không phải nơi quyết định có xóa credentials sau xác thực hay không. **DaoAuthenticationProvider** sử dụng UserDetailsService và PasswordEncoder để kiểm tra password cho flow username/password thông thường.

**PasswordEncoder** có thể cần password hash trong UserDetails để gọi matches(raw, encoded). Vì vậy điểm xóa credentials mặc định được thực hiện **sau khi xác thực đã thành công**, chứ không nên tự ý xóa password hash trước lúc kiểm tra.

## 3. ProviderManager.eraseCredentialsAfterAuthentication hoạt động thế nào?

Trong kiến trúc Spring Security, **ProviderManager** điều phối các AuthenticationProvider phù hợp. Sau khi nhận kết quả xác thực thành công, ProviderManager có cơ chế xóa credentials khỏi kết quả nếu được bật.

Thuộc tính đáng chú ý:

- **eraseCredentialsAfterAuthentication**: thông thường **true theo mặc định** trong ProviderManager.
- Khi có kết quả thành công và kết quả hỗ trợ **CredentialsContainer**, ProviderManager gọi **eraseCredentials()** trên kết quả.
- Nếu tắt thuộc tính này, ProviderManager không thực hiện bước xóa tự động đó; việc tắt thường làm tăng nguy cơ lưu giữ thông tin nhạy cảm lâu hơn và **không phải giải pháp ưu tiên** cho lỗi cache.

Mã khái niệm, **không phải source code nguyên văn** của framework:

~~~java
Authentication result = provider.authenticate(requestAuthentication);

if (result != null && eraseCredentialsAfterAuthentication
        && result instanceof CredentialsContainer container) {
    container.eraseCredentials();
}

return result;
~~~

Hành vi thực tế còn có xử lý lựa chọn provider, exception, event, parent AuthenticationManager và các nhánh khác. Fragment trên chỉ nhấn mạnh **thời điểm sau xác thực** và lời gọi đến **CredentialsContainer**.

### CredentialsContainer là gì?

**org.springframework.security.core.CredentialsContainer** biểu thị một đối tượng hỗ trợ xóa thông tin credentials. Interface quan trọng có method:

~~~java
void eraseCredentials();
~~~

Đối tượng **UsernamePasswordAuthenticationToken** có khả năng xóa credentials. Trong các triển khai thường gặp, việc erase không chỉ làm trường credentials thành null, mà còn có thể **gọi eraseCredentials trên những đối tượng liên quan nếu chúng triển khai CredentialsContainer**.

Ví dụ đáng chú ý:

- Kết quả UsernamePasswordAuthenticationToken chứa **credentials là raw password**: sau erase, credentials thường thành **null**.
- Nếu **principal là org.springframework.security.core.userdetails.User** của Spring Security, lớp này cũng hỗ trợ CredentialsContainer: lời gọi erase có thể khiến **password trong User principal** thành **null**.
- Nếu principal là một lớp UserDetails tự viết **không** triển khai CredentialsContainer, việc xóa tự động có thể **không làm sạch các trường mật khẩu riêng của lớp ấy**. Không suy ra mọi object nested sẽ luôn được xóa.
- Nếu một UserDetails object đang được nhiều cấu phần cùng giữ reference, thay đổi password trong object ấy có thể được các cấu phần còn lại nhìn thấy.

Không có nghĩa các giá trị trong user database bị sửa. Đây là thay đổi trên **object đang ở trong bộ nhớ của JVM** và có thể ảnh hưởng cache nếu cache chứa cùng object.

### Erase không đồng nghĩa zero hóa mọi byte

Trong Java, **String là immutable**. Gán credentials = null hoặc xóa trường tham chiếu không bảo đảm mảng byte từng chứa mật khẩu được ghi đè an toàn ngay lập tức. Đối tượng, heap dump, log, trace hoặc các bản sao khác có thể đã giữ dữ liệu trước đó.

Vì vậy cần kết hợp:
- Không ghi password, Authorization header, bearer token vào log.
- Dùng HTTPS và bảo vệ request.
- Không gán raw password vào session hoặc cache.
- Giảm thời gian và phạm vi tồn tại của secret trong bộ nhớ.
- Xử lý heap dump, crash dump và công cụ quan sát sản phẩm theo chính sách bảo mật.

Cơ chế erase của Spring Security là **giảm thiểu lưu giữ credentials**, không phải bảo đảm xóa bí mật hoàn toàn khỏi toàn bộ tiến trình.

## 4. Phân biệt bốn nơi có thể giữ thông tin đăng nhập

| Nơi chứa | Thông tin thường có | Có nên giữ raw password? | Ghi chú |
| --- | --- | --- | --- |
| Request Authentication trước xác thực | Username + raw password từ client | Chỉ trong thời gian xử lý cần thiết | Được filter/provider sử dụng |
| UserDetails từ UserDetailsService | Username, **password hash**, flags, authorities | **Không** | Hash cần cho PasswordEncoder.matches |
| Authentication thành công trong SecurityContext | Principal + authorities, trạng thái xác thực | Thông thường **không cần** | ProviderManager có thể erase credentials |
| User cache / UserDetails cache | UserDetails đã tải để giảm truy vấn | **Không**; có thể cần hash để xác thực lần tới | Phải tránh chia sẻ instance bị erase |

**Password hash không phải raw password**, nhưng vẫn là dữ liệu nhạy cảm. Hash cần thuật toán lưu mật khẩu phù hợp như BCrypt/Argon2 với tham số thích hợp, không phải một phép băm nhanh chung dùng trực tiếp. Nếu cache giữ hash, cache vẫn cần kiểm soát TTL, phạm vi truy cập, thay đổi mật khẩu và thu hồi tài khoản.

**Authentication đã xác thực không nhất thiết phải giữ nguyên UserDetails:** tùy provider, principal có thể là String, UserDetails hoặc object của cơ chế OAuth2/OIDC. Quy tắc xóa cụ thể phụ thuộc kiểu đối tượng và việc triển khai CredentialsContainer. Không xây dựng logic bảo mật dựa trên giả định mọi principal đều có getPassword().

## 5. Điểm xung đột: cache giữ cùng object với principal

Xét một UserDetailsService tự viết như sau:

~~~java
// Minh họa lỗi chia sẻ đối tượng; không đưa nguyên mẫu này vào production.
public final class SharedInstanceUserDetailsService implements UserDetailsService {

    private final UserDetails cachedUser;

    public SharedInstanceUserDetailsService(PasswordEncoder encoder) {
        cachedUser = User.withUsername("learner")
            .password(encoder.encode("learner-pass"))
            .roles("USER")
            .build();
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        if (!cachedUser.getUsername().equals(username)) {
            throw new UsernameNotFoundException(username);
        }
        return cachedUser; // Trả lại CHÍNH object đang được giữ trong cache.
    }
}
~~~

Đoạn này có thể biên dịch khi thêm các import từ Spring Security và dùng trong ứng dụng đã cấu hình PasswordEncoder; mục đích của nó là mô tả **một cách triển khai có lỗi**, không phải bài tập khuyến khích chạy ngoài môi trường kiểm soát.

Dòng chảy:

~~~text
Lần 1:
cache.originalUser.password = "$2a$...hash..."
       |
loadUserByUsername -> trả về chính cachedUser
       |
DaoAuthenticationProvider tạo Authentication(principal = cachedUser)
       |
ProviderManager xóa credentials sau xác thực
       |
UsernamePasswordAuthenticationToken.eraseCredentials()
       |
principal triển khai CredentialsContainer -> principal.eraseCredentials()
       |
cache.originalUser.password = null  (do cùng reference)

Lần 2:
loadUserByUsername -> trả về object cachedUser cũ
       |
PasswordEncoder.matches(rawPassword, cachedUser.getPassword())
       |
hash đã null -> kiểm tra mật khẩu không thể thành công như bình thường
~~~

Đối với UserDetailsService cache trực tiếp trả cùng instance mutable, lần sau thường dẫn đến xác thực thất bại hoặc lỗi về password hash bị thiếu, tùy cách provider/encoder xử lý. Với những cache khác, hệ thống có thể fallback về dữ liệu gốc, khiến cache mất tác dụng nhưng request vẫn thành công. Điều quan trọng không phải dự đoán duy nhất mã 401, mà là **cache đã bị thay đổi ngoài ý muốn** bởi cơ chế bảo mật.

### Cái nào bị xóa?

Nếu cùng object UserDetails nằm ở:

1. Cache, có một reference.
2. Authentication principal, có thêm reference đến **cùng instance**.
3. ProviderManager gọi eraseCredentials trên Authentication.
4. Authentication đệ quy yêu cầu principal xóa credentials.

Thì **password trên instance chung** bị xóa. Đây là hiệu ứng **aliasing/reference sharing** trong Java. Không phải PasswordEncoder đã sửa hash trên database, cũng không phải framework tự tìm và xóa tất cả mục trong cache.

### UserCache có phải được bật mặc định không?

**Không nên nhầm mọi ứng dụng có UserDetailsService là đang có user cache.** Với DaoAuthenticationProvider/AbstractUserDetailsAuthenticationProvider, cơ chế UserCache có interface riêng và cấu hình mặc định thông thường là **NullUserCache** (không lưu dữ liệu người dùng giữa các lần tìm). Caching thường được bật chủ động hoặc xuất hiện tại tầng UserDetailsService bằng một cache như ConcurrentHashMap, Caffeine, Redis, @Cacheable hoặc proxy khác.

Nếu chỉ dùng **InMemoryUserDetailsManager**, nó là một user store trong bộ nhớ. Khi thiết kế kiểm thử hoặc sử dụng đối tượng UserDetails trực tiếp, vẫn cần quan sát liệu đối tượng trả về có chia sẻ reference với store hay không. Đừng suy ra từ tên “in-memory” rằng mọi cấu hình đều có cùng hành vi caching hoặc xóa.

Nếu bạn tự cấu hình **UserCache** trên provider, việc cache trả về cùng instance UserDetails rồi bị erase cũng cần được xem xét. Trong một số đường đi, provider có thể thử tải lại từ UserDetailsService khi dữ liệu cache không xác thực được; điều này có thể che bớt lỗi nhưng tạo truy vấn dư thừa và khiến cache không hiệu quả.

## 6. Cách thiết kế được ưu tiên: giữ erase mặc định và trả bản sao độc lập

Mô hình ổn định là:

- **Bộ nhớ đệm giữ bản gốc** có username, password hash, trạng thái account và authorities ở nơi được bảo vệ.
- **Mỗi lượt xác thực nhận bản sao riêng** của UserDetails thay vì cùng instance lưu trong cache.
- ProviderManager có thể **erase credentials trên principal bản sao** mà không làm mất password hash của bản gốc.
- Request tiếp theo lại lấy một bản sao mới từ nguồn cache còn nguyên.
- Thay đổi mật khẩu/role/trạng thái tài khoản phải có chiến lược **invalidate/refresh cache** thích hợp.

Sơ đồ:

~~~text
Cache (UserDetails nguồn: passwordHash còn nguyên)
   |
   +-- create defensive copy #1
   |       |
   |       +--> DaoAuthenticationProvider xác thực thành công
   |       +--> ProviderManager.eraseCredentials()
   |       +--> copy #1.password = null
   |
   +-- create defensive copy #2
           |
           +--> lần xác thực thứ hai vẫn có password hash đúng
           +--> copy #2 được erase độc lập
~~~

**Tránh chỉ copy reference.** Gán biến mới như **UserDetails other = cached;** vẫn trỏ cùng object. Để bảo vệ bản gốc, phải tạo object mới không dùng chung trường mutable có thể bị xóa.

Với **org.springframework.security.core.userdetails.User**, Spring Security cung cấp **User.withUserDetails(existing).build()** để tạo UserDetails mới từ giá trị của đối tượng có sẵn. Cách này phù hợp ví dụ đơn giản khi các thành phần bên trong không bị chia sẻ mutable ngoài ý muốn.

Nếu principal tùy biến chứa token, byte array, credential map hoặc đối tượng mutable lồng sâu, bạn cần kiểm tra **defensive copy đủ sâu** theo cấu trúc đó, tránh sao chép nông rồi vẫn chia sẻ dữ liệu nhạy cảm.

## 7. Ví dụ Spring Boot hoàn chỉnh: xóa credentials nhưng giữ cache an toàn

### 7.1. Phiên bản và kết quả cần quan sát

Ví dụ sử dụng **Java 17+**, **Spring Boot 3.3.13**, Spring Security 6 và Maven. Ứng dụng bật **HTTP Basic** để dễ thử nhiều lần xác thực bằng curl, dùng **BCryptPasswordEncoder** và một user cache mô phỏng. Chính UserDetailsService sẽ trả **bản sao mới** cho từng lượt gọi.

Với request có credentials hợp lệ, API /me trả các cờ **true** xác nhận credentials trong Authentication đã được xóa. Sau hai request độc lập, cache nguồn vẫn còn password hash; đây là điều bài học muốn chứng minh.

Các tệp:

~~~text
credentials-erasure-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/erasure/
    │   ├── ErasureDemoApplication.java
    │   ├── SecurityConfig.java
    │   ├── CopyingUserDetailsService.java
    │   └── AccountController.java
    └── test/java/com/example/erasure/
        └── CredentialsErasureTest.java
~~~

### 7.2. pom.xml

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
    <artifactId>credentials-erasure-demo</artifactId>
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

Starter dependencies được Spring Boot parent quản lý version; tránh tự ghép những bản Spring Framework/Security không tương thích. Trong ví dụ này không thêm database: cache chỉ là ConcurrentHashMap trong một JVM.

### 7.3. ErasureDemoApplication.java

~~~java
package com.example.erasure;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErasureDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErasureDemoApplication.class, args);
    }
}
~~~

Cả bốn lớp nguồn nằm cùng package com.example.erasure để Spring Boot tìm thấy SecurityConfig và AccountController.

### 7.4. CopyingUserDetailsService.java

~~~java
package com.example.erasure;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class CopyingUserDetailsService implements UserDetailsService {

    // Dữ liệu gốc nằm trong cache. Không trả trực tiếp instance này cho provider.
    private final Map<String, UserDetails> cache = new ConcurrentHashMap<>();

    public CopyingUserDetailsService(PasswordEncoder passwordEncoder) {
        UserDetails learner = User.withUsername("learner")
            .password(passwordEncoder.encode("learner-pass"))
            .roles("USER")
            .build();

        cache.put(learner.getUsername(), learner);
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {

        UserDetails source = cache.get(username);

        if (source == null) {
            throw new UsernameNotFoundException("Unknown user");
        }

        // Điểm cốt lõi: trả object User mới, không chia sẻ instance gốc.
        return User.withUserDetails(source).build();
    }

    // Chỉ dùng trong test: cho biết cache gốc còn hash, không làm lộ hash.
    public boolean cacheRetainsPasswordHash(String username) {
        UserDetails source = cache.get(username);
        return source != null
            && source.getPassword() != null
            && !source.getPassword().isBlank();
    }
}
~~~

**Điểm quan trọng của class này:**

1. **cache** giữ một UserDetails gốc có BCrypt hash.
2. **loadUserByUsername** lấy bản gốc nhưng **trả một User object mới** thông qua User.withUserDetails(...).build().
3. **DaoAuthenticationProvider** có thể dùng password hash trên bản sao để so mật khẩu.
4. **ProviderManager** sau khi xác thực có thể xóa password trong principal bản sao; bản gốc trong ConcurrentHashMap không bị thay đổi.
5. Phương thức cacheRetainsPasswordHash chỉ trả boolean cho kiểm thử. Nó không trả password hash, không phải endpoint production.
6. ConcurrentHashMap hỗ trợ truy cập đồng thời nhưng **không tự giải quyết TTL, invalidation, thay đổi password, account lockout, phân tán cache**. Những vấn đề đó phải thiết kế bổ sung cho hệ thống thật.

Đây là cache học tập. Với hệ thống thật, có thể lưu UserDetails bằng Caffeine/Redis hoặc cơ chế dữ liệu khác; nguyên tắc không chia sẻ cùng object bị erase vẫn áp dụng đối với mỗi implementation có mutable principal.

### 7.5. SecurityConfig.java

~~~java
package com.example.erasure;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    CopyingUserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new CopyingUserDetailsService(encoder);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/me").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }
}
~~~

**Giải thích lựa chọn:**

- Bean **CopyingUserDetailsService** implements UserDetailsService, được Spring Security dùng làm user store cho xác thực username/password. Khi Spring Security tạo provider chuẩn, PasswordEncoder bean hỗ trợ kiểm tra BCrypt hash.
- **httpBasic** nhận credentials từ mỗi request. Cặp username/password trong header Basic chỉ là Base64 biểu diễn, không phải mã hóa an toàn; trong production bắt buộc HTTPS.
- **SessionCreationPolicy.STATELESS** ngăn Spring Security dựa vào HttpSession để nhớ Authentication qua request; vì vậy các lần gọi có credentials sau đây được kiểm chứng độc lập, rõ tác động cache.
- **formLogin(disable)** tránh redirect trang đăng nhập và giúp request không credentials tới /me nhận 401 từ cơ chế Basic.
- **Không cấu hình ProviderManager.setEraseCredentialsAfterAuthentication(false)**. Ví dụ chủ động giữ mặc định xóa credentials để quan sát sự khác nhau giữa principal đã bị xóa và bản sao cache còn nguyên.
- Ví dụ chỉ sử dụng GET. Nếu mở rộng POST/PUT/DELETE, đừng tự động tắt CSRF chỉ vì dùng HTTP Basic/STATELESS: trình duyệt có thể tự gửi Basic credentials đã nhớ, nên vẫn cần xác định threat model và cơ chế chống CSRF.

**Lưu ý:** SessionCreationPolicy.STATELESS không phải là tính năng erase credentials. Nó liên quan việc lưu/tải SecurityContext giữa các request. Hai chính sách giải quyết hai trách nhiệm khác nhau.

### 7.6. AccountController.java

~~~java
package com.example.erasure;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public");
    }

    @GetMapping("/me")
    public Map<String, Object> me(Authentication authentication) {
        Object principal = authentication.getPrincipal();

        boolean principalPasswordErased =
            principal instanceof UserDetails details
                && details.getPassword() == null;

        return Map.of(
            "username", authentication.getName(),
            "credentialsErased", authentication.getCredentials() == null,
            "principalPasswordErased", principalPasswordErased
        );
    }
}
~~~

Endpoint /me chỉ trả **cờ boolean** để chứng minh cơ chế xóa. Không trả raw password, password hash, Authorization header hoặc toàn bộ Authentication. Với flow UserDetails trong ví dụ, principal là org.springframework.security.core.userdetails.User nên principalPasswordErased dự kiến true sau khi ProviderManager xử lý kết quả.

Không tái sử dụng cách kiểm tra principalPasswordErased này như điều kiện quyết định phân quyền. Với JWT hoặc principal tùy biến, password không nhất thiết là thuộc tính có nghĩa. **Xóa credentials** và **cho phép truy cập** là hai trách nhiệm khác nhau.

## 8. Chạy ứng dụng và quan sát hai lần xác thực

Tại thư mục credentials-erasure-demo có pom.xml:

~~~bash
mvn spring-boot:run
~~~

Mở một terminal khác. Trên PowerShell cũ, dùng **curl.exe** thay vì alias curl nếu cần.

### 8.1. Request chưa đăng nhập

~~~bash
curl -i http://localhost:8080/me
~~~

Trọng tâm kết quả:

~~~http
HTTP/1.1 401
WWW-Authenticate: Basic realm="Realm"
~~~

Header cụ thể có thể thay đổi theo cấu hình hoặc container, nhưng response không có kết quả /me vì chưa xác thực.

### 8.2. Request hợp lệ lần đầu

~~~bash
curl -i -u learner:learner-pass http://localhost:8080/me
~~~

Kết quả trọng tâm dự kiến là **HTTP 200**, với các giá trị JSON:

~~~json
{
  "username": "learner",
  "credentialsErased": true,
  "principalPasswordErased": true
}
~~~

Thứ tự các khóa JSON không phải cố định. **credentialsErased = true** nghĩa là Authentication kết quả đã không còn credentials trong field tương ứng. **principalPasswordErased = true** nghĩa là User principal thuộc flow này đã bị xóa password. Không kết luận rằng mọi bản sao password trong JVM đã bị zero hóa.

### 8.3. Request hợp lệ lần hai

Gọi lại cùng lệnh:

~~~bash
curl -i -u learner:learner-pass http://localhost:8080/me
~~~

Kết quả vẫn phải là **HTTP 200** với các cờ tương tự. Vì UserDetailsService trả **bản sao mới** cho mỗi lần xác thực, password hash gốc trong cache không mất đi sau request thứ nhất.

### 8.4. Request sai password

~~~bash
curl -i -u learner:wrong-pass http://localhost:8080/me
~~~

Trọng tâm kết quả là **401 Unauthorized**. Việc cache còn nguyên hash đúng **không có nghĩa** mật khẩu sai được chấp nhận.

### 8.5. Request GET công khai

~~~bash
curl -i http://localhost:8080/public
~~~

Trọng tâm kết quả là **200 OK** và JSON có message = "public". Endpoint này không yêu cầu credentials.

| Request | Status dự kiến | Điều được kiểm chứng |
| --- | --- | --- |
| GET /me không Basic header | 401 | Chưa xác thực, không có quyền |
| GET /me Basic hợp lệ lần 1 | 200 | Mật khẩu được kiểm tra, credentials của Authentication thành công đã erase |
| GET /me Basic hợp lệ lần 2 | 200 | Cache gốc còn hash vì trả defensive copy |
| GET /me Basic sai password | 401 | Cache không làm mất bước kiểm tra credentials |
| GET /public không Basic header | 200 | Cho phép truy cập công khai |

Phép thử HTTP trên chỉ cho thấy kết quả request. Kiểm thử tự động ở mục tiếp theo sẽ kiểm tra trực tiếp **cache gốc vẫn còn password hash** sau cả hai request, tránh chỉ suy luận từ status 200.

## 9. Kiểm thử tự động với MockMvc: chứng minh cache không bị erase

Tạo **src/test/java/com/example/erasure/CredentialsErasureTest.java**:

~~~java
package com.example.erasure;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class CredentialsErasureTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    CopyingUserDetailsService users;

    @Test
    void credentialsAreErasedButCacheCanAuthenticateAgain() throws Exception {
        assertTrue(users.cacheRetainsPasswordHash("learner"));

        mvc.perform(get("/me").with(httpBasic("learner", "learner-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"))
            .andExpect(jsonPath("$.credentialsErased").value(true))
            .andExpect(jsonPath("$.principalPasswordErased").value(true));

        // Đây là object gốc trong cache, không phải principal bản sao.
        assertTrue(users.cacheRetainsPasswordHash("learner"));

        mvc.perform(get("/me").with(httpBasic("learner", "learner-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"))
            .andExpect(jsonPath("$.credentialsErased").value(true))
            .andExpect(jsonPath("$.principalPasswordErased").value(true));

        assertTrue(users.cacheRetainsPasswordHash("learner"));
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mvc.perform(get("/me").with(httpBasic("learner", "wrong-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void missingCredentialsAreRejected() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Bài kiểm thử này phân biệt **hai trạng thái tồn tại đồng thời**:

1. Principal thuộc kết quả Authentication đã bị erase credentials, nhằm giảm thời gian giữ bí mật.
2. Bản gốc trong cache vẫn có password hash để tiếp tục xác thực ở request độc lập tiếp theo.

Nếu bạn thử thay **return User.withUserDetails(source).build();** bằng **return source;** trong CopyingUserDetailsService, test có thể phát hiện cache mất hash sau lần xác thực đầu tiên. Thực nghiệm đó chỉ nên làm trong bản nháp/local, rồi khôi phục defensive copy. Kết quả cụ thể còn tùy provider và phiên bản nhưng **assertTrue(cacheRetainsPasswordHash(...))** trực tiếp kiểm tra hiện tượng chia sẻ object.

### Phân biệt kiểm thử Mockito và kiểm thử tích hợp

Mocking PasswordEncoder hoặc DaoAuthenticationProvider quá mạnh có thể khiến bạn bỏ qua chính lời gọi eraseCredentials thật. Test MockMvc phía trên chạy qua Spring Security filter chain và luồng HTTP Basic với provider của ứng dụng, nên phù hợp hơn để quan sát tương tác của nhiều thành phần.

Nếu ứng dụng dùng custom AuthenticationManager thay vì cơ chế do Spring tự cấu hình, test cần bảo đảm Manager ấy thực sự được sử dụng. Không ghi chữ “erase thành công” chỉ vì bạn gọi thủ công phương thức eraseCredentials trong test mà không kiểm tra request đi qua ProviderManager.

## 10. Sửa lỗi cache ở tầng nào?

Không phải ứng dụng nào cũng dùng cùng kiến trúc cache, vì vậy cần xác định đối tượng nào đang bị chia sẻ.

### Trường hợp A: UserDetailsService có cache riêng

Ví dụ UserDetailsService dùng một Map hoặc @Cacheable để trả UserDetails.

**Nguy cơ:** object được trả ra chính là object trong cache. Nếu principal giữ cùng instance và implements CredentialsContainer, cache bị mất hash.

**Giải pháp:** repository/cache giữ object gốc; tại ranh giới loadUserByUsername, trả **bản sao độc lập**. Đối với custom UserDetails, bảo đảm bản sao thực sự độc lập đối với các field có thể bị mutate/erase.

### Trường hợp B: Cấu hình UserCache trên DaoAuthenticationProvider

Một số ứng dụng tự bật UserCache trên provider để tránh gọi UserDetailsService cho mỗi lần xác thực.

**Nguy cơ:** provider có thể lưu cùng UserDetails instance mà Authentication principal sẽ tham chiếu và bị erase sau xác thực. Khi đọc lại, bản cache không còn hash, provider cần tải lại hoặc có thể thất bại tùy đường đi. Một fallback tải lại dữ liệu có thể khiến hệ thống “vẫn login được” nhưng cache không còn hiệu quả.

**Giải pháp:** kiểm tra đường đi **lưu vào cache**, **trả từ cache**, **principal được đặt trong Authentication** và **lời gọi erase**. Đánh giá copy-on-write/copy-on-read hoặc cách quản lý cache khác để không chia sẻ instance mutable bị erase. Kiểm chứng bằng test hai lần xác thực thực tế.

### Trường hợp C: Custom UserDetails implements CredentialsContainer

Đối tượng custom có thể viết:

~~~java
@Override
public void eraseCredentials() {
    this.passwordHash = null;
}
~~~

Đây là **fragment của class custom**, không phải chương trình độc lập. Nếu cùng object được cache, effect tương tự. Nếu cố sửa bằng cách làm eraseCredentials không làm gì, bạn có thể giữ lại credentials trên principal lâu hơn dự kiến.

**Giải pháp:** quyết định rõ object nào được dùng như **cached identity record**, object nào là **authenticated principal**, và chỉ cho cơ chế erase thay đổi instance được phép bị xóa. Đừng dùng một entity JPA mutable duy nhất vừa làm nguồn cache vừa làm principal cho mọi request.

### Trường hợp D: AuthenticationProvider tự viết

Một AuthenticationProvider custom có thể trả Authentication chứa:

- credentials là raw password;
- principal là entity mang password hash;
- details chứa dữ liệu nhạy cảm;
- object không triển khai CredentialsContainer đúng.

**Nguy cơ:** mặc dù ProviderManager có cấu hình xóa mặc định, nó chỉ tác động đến object được hỗ trợ; các trường nhạy cảm ngoài contract vẫn còn.

**Giải pháp:** thiết kế Authentication success với thông tin tối thiểu, ưu tiên principal không mang password, hoặc triển khai CredentialsContainer phù hợp. Với provider custom, xác minh kết quả sau erase và kiểm tra không làm hỏng cache/nguồn dữ liệu.

### Trường hợp E: Principal đã nằm trong HttpSession

Sau form login, SecurityContext có thể được lưu qua HttpSession. Nếu Authentication đã bị erase trước khi lưu, principal có thể giữ username và authorities nhưng không còn password. **Đây thường là điều mong muốn**, vì request sau không cần hash để xác minh lại password theo flow session.

Đừng viết business logic yêu cầu **authentication.getCredentials()** hoặc **((UserDetails) principal).getPassword()** để xử lý nghiệp vụ sau login. Các giá trị này có thể đã bị xóa và không phải API để truy xuất mật khẩu đã đăng nhập.

## 11. Có nên tắt eraseCredentialsAfterAuthentication?

ProviderManager có setter:

~~~java
providerManager.setEraseCredentialsAfterAuthentication(false);
~~~

Đây là **một dòng minh họa trên đối tượng ProviderManager đã có sẵn**, không phải cấu hình hoàn chỉnh để dán vào Spring Boot. Lệnh này có thể tránh việc ProviderManager gọi erase trên kết quả thành công, nên đôi lúc được nhắc tới như một cách giảm tác động lên cache có object dùng chung.

Tuy nhiên, **không nên xem nó là giải pháp mặc định**:

- Raw password hoặc credentials khác có thể tồn tại trong Authentication lâu hơn.
- Authentication có thể được đặt vào SecurityContext và có thể được lưu trong HttpSession, cache hoặc công cụ quan sát.
- Lỗi thiết kế chia sẻ mutable object giữa cache và principal vẫn chưa được giải quyết.
- Khi ứng dụng chuyển cơ chế xác thực, hậu quả giữ credentials có thể khó phát hiện.
- Một người đọc code dễ suy ra rằng credentials đã được xóa theo cơ chế chuẩn trong khi bạn đã tắt nó.

**Ưu tiên:** giữ erase mặc định và **tách bản nguồn cache khỏi object principal**. Chỉ đánh giá việc tắt nếu đã xác định nhu cầu đặc biệt, mô hình nguy cơ, cách lưu Authentication và có test về retention của bí mật.

### Không tự xóa password hash khỏi DB

Việc eraseCredentials của một UserDetails object thành công **không** có nghĩa phải cập nhật password hash trong database thành null. Password hash là dữ liệu cần cho lần xác thực username/password tiếp theo. Chỉ xóa hoặc thay hash trong DB khi có nghiệp vụ cụ thể như reset/đổi mật khẩu, khóa account theo chính sách, hoặc xóa tài khoản đúng quy trình.

## 12. Ranh giới với SecurityContextRepository, session và stateless

Ba khái niệm thường xuất hiện cùng nhau nhưng làm việc khác nhau:

| Khái niệm | Trả lời câu hỏi nào? | Tác động chính |
| --- | --- | --- |
| **ProviderManager / eraseCredentialsAfterAuthentication** | Kết quả xác thực có còn giữ credentials không? | Thay đổi dữ liệu nhạy cảm trong Authentication thành công |
| **SecurityContextHolder / SecurityContextRepository** | Ngữ cảnh xác thực được dùng và lưu/tải ở đâu? | Duy trì Authentication trong request hoặc giữa request |
| **SessionCreationPolicy** | Spring Security tạo/dùng HttpSession thế nào? | Quyết định chiến lược stateful/stateless ở cấp chain |

Ví dụ:

- Với **form login + session**, login diễn ra một lần, Authentication đã bị erase có thể được lưu trong session và request sau nạp lại danh tính. Không cần dùng password hash từ principal cho mỗi lần xem trang.
- Với **HTTP Basic stateless**, mỗi request mang Basic credentials và có thể đi qua xác thực mới; UserDetailsService có thể được gọi nhiều lần. Vì vậy cache UserDetails bị mất password hash dễ bộc lộ lỗi khi request tiếp theo đến.
- Với **OAuth2 Resource Server + bearer token**, xác thực token theo từng request có thể tạo loại Authentication khác; cơ chế xóa và dữ liệu principal tùy loại token/provider. Không áp mô hình UserDetails chứa password hash lên mọi resource server.

**Quan trọng:** Erase credentials không đồng nghĩa logout và không hủy quyền trong SecurityContext. Nếu Authentication vẫn có principal/authorities hợp lệ, request hiện tại vẫn có thể được authorize. Ngược lại, chọn STATELESS cũng không tự tắt erase credentials.

## 13. Xử lý password change, role change và account disable khi có cache

Bảo vệ object khỏi erase là **điều kiện cần**, chưa phải toàn bộ thiết kế user cache an toàn.

### Đổi mật khẩu

Nếu database đã đổi password hash nhưng cache còn hash cũ, người dùng có thể tiếp tục xác thực bằng mật khẩu cũ cho đến khi cache được refresh/evict, tùy kiến trúc. Cần invalidation sau password change và kiểm thử thời điểm thay đổi có hiệu lực.

### Đổi quyền hoặc khóa tài khoản

Nếu authorities/account flags được cache quá lâu, user bị thu hồi role hoặc khóa account vẫn có thể được hệ thống chấp nhận theo bản cache cũ. Đặt TTL và eviction phù hợp; hệ thống nhạy cảm có thể cần kiểm tra trạng thái authoritative tại mỗi bước quan trọng.

### Đồng bộ nhiều node

Cache trong ConcurrentHashMap chỉ sống trong một JVM. Các node khác nhau có thể giữ phiên bản UserDetails khác nhau. Cần chia sẻ tín hiệu invalidation hoặc chiến lược caching phân tán nếu production có nhiều instance.

### Không cache raw password

Cache dữ liệu user thường chỉ nên giữ **password hash**, trạng thái tài khoản và authorities cần thiết. Không lưu raw password, session cookie hoặc Authorization header thành cache key/value.

### Tránh key và logging lộ thông tin

Sử dụng key ổn định cho user record; tránh đưa password/token vào key. Dùng log đã redacted, phân quyền truy cập cache và quản lý telemetry để không lộ dữ liệu nhạy cảm.

### Cân nhắc cache miss, concurrency và thundering herd

Khi một user bị evict, nhiều request đồng thời có thể cùng truy vấn database. Dùng cache loader có đồng bộ/throttling phù hợp khi tải lớn, và đảm bảo mỗi Authentication nhận dữ liệu đúng sau khi có password/role change. Không dùng lock toàn cục giữ qua network call nếu không có thiết kế rõ ràng.

## 14. Chẩn đoán lỗi “login đầu tiên được, login thứ hai lỗi”

Đi theo thứ tự thay vì lập tức tắt erase:

1. **Xác nhận loại flow:** form login với session hay HTTP Basic/JWT stateless? Request sau thực sự yêu cầu xác thực lại không?
2. **Xác nhận chain đúng:** SecurityFilterChain nào xử lý path đó? Có nhiều chain với SessionCreationPolicy khác nhau không?
3. **Xác nhận AuthenticationManager:** có phải ProviderManager tiêu chuẩn, có bật eraseCredentialsAfterAuthentication mặc định không?
4. **Kiểm tra principal type:** UsernamePasswordAuthenticationToken có chứa UserDetails implements CredentialsContainer không? Có provider custom nào trả loại principal khác không?
5. **Kiểm tra nguồn UserDetails:** UserDetailsService có @Cacheable, Map, UserCache hoặc thư viện cache khác không?
6. **Kiểm tra reference sharing:** cache trả chính instance hay tạo bản sao? Có nested mutable credentials được share không?
7. **Quan sát sau request thành công:** password hash **trên bản gốc cached UserDetails** còn nguyên hay đã null? Kiểm tra trong test an toàn, không in giá trị hash.
8. **Quan sát request tiếp:** có cache hit, có fallback gọi lại UserDetailsService, có bị authentication failure hoặc retry không?
9. **Kiểm tra thay đổi user thật:** mật khẩu, role, khóa tài khoản, TTL và invalidation có đang khiến cache stale không?
10. **Thử bản sao độc lập:** giữ erase mặc định, thêm defensive copy, chạy lại hai request và test hash cache không bị thay đổi.

**Không log raw credentials**, encoded password, Authorization header hoặc toàn bộ principal để “chứng minh” vấn đề. Test chỉ cần boolean/identity assertions và số lần tải nguồn nếu cần.

### Các dấu hiệu thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Request đầu 200, request sau 401 | UserDetails cache dùng cùng object và bị erase password | Trả defensive copy, giữ cache source độc lập |
| Request vẫn 200 nhưng database query tăng sau request đầu | Provider fallback tải UserDetails mới vì cached object đã bị xóa | Kiểm tra UserCache object identity, copy hoặc cache strategy |
| Authentication principal password null | Cơ chế erase đang hoạt động | Thường **đúng**, không phải lỗi nếu nghiệp vụ không dùng password |
| Cache source password null | Cache đã bị thay đổi ngoài ý muốn | Tách instance nguồn và principal |
| Password cũ vẫn xác thực sau đổi mật khẩu | Cache stale, chưa invalidate | Evict/reload đúng thời điểm; kiểm thử revocation |
| Role bị thu hồi nhưng còn hiệu lực | Cache authorities stale hoặc session cũ | Thiết kế chính sách cập nhật session/authority và cache eviction |
| Tắt erase thì login chạy lại được | Có thể che lỗi reference sharing | Khôi phục erase và sửa cách cache trả UserDetails |
| Lỗi chỉ khi chạy song song nhiều request | Dùng mutable UserDetails chung hoặc cache update không an toàn | Xem khả năng đồng thời, snapshot/copy và cập nhật nguyên tử |

## 15. Những hiểu lầm cần tránh

**Hiểu lầm 1: Erase credentials xóa luôn password hash khỏi database.**  
Sai. ProviderManager/Authentication hoạt động trên object trong JVM; việc DB thay đổi cần một thao tác lưu dữ liệu rõ ràng.

**Hiểu lầm 2: Authentication principal luôn giữ raw password.**  
Sai. Principal có thể là UserDetails, String hoặc object khác; raw password thường nằm trong credentials đầu vào và có thể bị xóa khỏi kết quả.

**Hiểu lầm 3: User cache luôn bật khi có UserDetailsService.**  
Sai. DaoAuthenticationProvider không mặc định phải cache user. Những tầng cache khác có thể do ứng dụng thêm vào.

**Hiểu lầm 4: Tắt erase là cách chuẩn để sửa cache.**  
Không nên. Cần sửa đối tượng được chia sẻ và giữ cơ chế giảm lưu giữ bí mật nếu có thể.

**Hiểu lầm 5: Bản sao chỉ là gán biến mới.**  
Sai. Gán cùng reference không tách instance; cần clone/copy thật, và kiểm tra các nested mutable field.

**Hiểu lầm 6: Đã erase thì mọi byte mật khẩu chắc chắn biến mất khỏi RAM.**  
Sai. Java String immutable, có thể tồn tại bản sao, log hoặc dump; erase là một biện pháp giảm thời gian lưu giữ.

**Hiểu lầm 7: Credentials bị xóa thì user bị logout.**  
Sai. Kết quả Authentication vẫn có principal và authorities, có thể duy trì authorization hợp lệ.

**Hiểu lầm 8: Nếu HTTP Basic luôn gửi password thì cache không cần hash.**  
Sai. Server vẫn cần hash gốc (hoặc cơ chế kiểm chứng authoritative) để kiểm tra credentials của request mới.

## 16. Bài tập tự kiểm tra

### Bài tập A — Phân biệt hai bản UserDetails

Một bộ nhớ đệm có object UserDetails tên cachedUser. UserDetailsService trả trực tiếp cachedUser và DaoAuthenticationProvider dùng nó làm principal. ProviderManager xóa credentials thành công. Sau đó cachedUser.getPassword() trở thành null. Vì sao?

**Đáp án:** principal và cachedUser trỏ cùng instance, và principal implements CredentialsContainer. Erase làm thay đổi object chung; cache nhìn thấy password null.

### Bài tập B — Sửa cache

Sửa câu lệnh trả về trong UserDetailsService để tránh làm hỏng cachedUser.

~~~java
return User.withUserDetails(cachedUser).build();
~~~

**Giải thích:** tạo UserDetails mới làm principal; bản cache nguồn không bị xóa khi instance mới bị erase. Với custom user type, phải sao chép đủ các trường liên quan và không share mutable credential.

### Bài tập C — Cấu hình sai mục tiêu

Đồng nghiệp đề xuất đổi SessionCreationPolicy từ STATELESS sang IF_REQUIRED để “ngăn việc mất hash trên cache”. Đề xuất có giải quyết tận gốc không?

**Đáp án:** Không. Session policy quyết định cách dùng session, không xử lý việc cùng UserDetails instance bị erase. Cần sửa copy/cache boundary.

### Bài tập D — Kiểm tra sau erase

Trong luồng username/password, Authentication.getCredentials() trả null sau xác thực thành công, nhưng principal vẫn có username và authorities. Hành vi này có phải lỗi không?

**Đáp án:** Thường là đúng. Đã xác thực thì không cần giữ raw password để phân quyền; Authentication vẫn giữ danh tính và quyền.

### Bài tập E — Vì sao chỉ nhìn HTTP 200 là chưa đủ?

Một user cache sau request đầu bị mất password hash, nhưng request sau vẫn 200 nhờ provider tải lại từ DB. Bạn có thể kết luận cache lành mạnh không?

**Đáp án:** Không. Cần kiểm tra source object trong cache, số cache hit/miss, số lần tải user và tác động của erase; provider fallback có thể che vấn đề.

### Bài tập F — Chọn chiến lược bảo mật

Có hai giải pháp: (1) tắt eraseCredentialsAfterAuthentication; (2) giữ erase mặc định và trả defensive copy từ cache. Với ứng dụng thông thường, chọn gì?

**Đáp án:** Ưu tiên (2) để vừa giữ password hash nguồn ổn định vừa giảm việc giữ raw credentials sau xác thực. Giải pháp (1) cần đánh giá bảo mật rất kỹ trong ngoại lệ cụ thể.

### Bài tập G — Cache stale

Một người dùng đổi password ở DB nhưng cache còn hash cũ, và UserDetailsService trả bản sao của cache cũ. Defensive copy có giải quyết việc đăng nhập bằng password cũ không?

**Đáp án:** Không. Defensive copy xử lý aliasing/erase, còn vấn đề cache stale cần TTL, eviction hoặc cơ chế cập nhật nguồn dữ liệu có thẩm quyền.

## 17. Checklist trước khi đưa vào production

- [ ] Đã hiểu **ProviderManager.eraseCredentialsAfterAuthentication** thông thường bật mặc định.
- [ ] Đã phân biệt **raw password**, **password hash**, **principal**, **Authentication** và **cached UserDetails**.
- [ ] Nếu dùng UserCache/UserDetailsService cache, đã kiểm tra aliasing với principal.
- [ ] Đã thực hiện **defensive copy** hoặc ranh giới dữ liệu phù hợp trước khi cache instance mutable bị erase được dùng.
- [ ] Đã chạy test **ít nhất hai lần xác thực thành công liên tiếp** và xác minh cache nguồn không bị sửa ngoài ý muốn.
- [ ] Đã kiểm thử mật khẩu sai, user không tồn tại, account bị khóa/hết hạn và invalidation sau đổi mật khẩu.
- [ ] Đã xác định chính sách TTL/evict cho password hash, role, trạng thái tài khoản.
- [ ] Không tắt erase chỉ để che lỗi cache; nếu ngoại lệ buộc phải tắt, đã có đánh giá bảo mật và test lưu giữ credentials.
- [ ] Không log raw password, password hash, cookie, Authorization header hay toàn bộ Authentication.
- [ ] Không dùng Authentication.getCredentials() hoặc principal.getPassword() làm dữ liệu nghiệp vụ sau login.
- [ ] Với nhiều node hoặc async, đã xét cache consistency, propagation và object sharing.
- [ ] Đã hiểu erase không tương đương xóa bí mật khỏi mọi bản sao RAM và không thay mã hóa/kiểm soát truy cập.
- [ ] Đã xác nhận hành vi theo đúng AuthenticationProvider/Authentication implementation của ứng dụng, đặc biệt nếu dùng OAuth2/JWT hoặc provider tùy biến.

**Ghi nhớ:** Sau xác thực username/password, **ProviderManager** thường xóa credentials khỏi Authentication để giảm lưu giữ thông tin nhạy cảm. Nếu principal là cùng **UserDetails object** đang nằm trong cache, lời gọi erase có thể làm mất password hash của cache. Giải pháp ưu tiên là **giữ cơ chế xóa mặc định, tách instance nguồn cache khỏi instance đưa vào xác thực, kiểm thử các request liên tiếp**, và quản lý cache invalidation theo thay đổi password/role/trạng thái account.

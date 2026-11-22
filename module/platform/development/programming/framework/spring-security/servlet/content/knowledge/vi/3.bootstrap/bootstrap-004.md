# Hành vi mặc định của Spring Security Servlet: tài khoản, mật khẩu sinh tự động và trang đăng nhập

## 1. Bức tranh tổng quát khi thêm Spring Security vào Spring Boot

Với một ứng dụng **Spring Boot Servlet** dùng Spring MVC, việc thêm dependency `spring-boot-starter-security` thường khiến hành vi HTTP thay đổi ngay cả khi lập trình viên chưa tự viết `SecurityFilterChain` hay biểu mẫu đăng nhập.

Trong trường hợp tiêu biểu — có starter Security trên classpath, ứng dụng không cung cấp cấu hình bảo mật web và không cung cấp hệ thống xác thực riêng — Spring Boot/Spring Security thiết lập:

1. **Bảo vệ các HTTP endpoint theo mặc định:** các request tới tài nguyên ứng dụng thông thường cần được xác thực trước khi truy cập.
2. **Hai cách xác thực mặc định:** form login cho luồng trình duyệt và HTTP Basic cho client phù hợp. Cách client nhận phản hồi chưa đăng nhập phụ thuộc cách request được xử lý và content negotiation.
3. **Một tài khoản trong bộ nhớ:** tên người dùng mặc định là `user`, thường có role `USER` và mật khẩu mạnh được tạo ngẫu nhiên khi ứng dụng khởi động.
4. **Trang đăng nhập do Spring Security sinh:** nếu form login được bật và không khai báo trang tùy chỉnh, truy cập `GET /login` có thể nhận HTML của framework mà không cần tự viết controller, JSP hoặc Thymeleaf.

Đây là **cấu hình hỗ trợ khởi đầu và phát triển**, không phải hệ thống tài khoản người dùng đầy đủ cho môi trường production. Nội dung dưới đây tập trung vào cơ chế mặc định, cách tự kiểm chứng, những điểm gây nhầm lẫn và thời điểm cần chuyển sang cấu hình chủ động.

**Phạm vi phiên bản:** ví dụ sử dụng Spring Boot 3.3.x, Spring Security 6.x và Java 17 trở lên (Jakarta Servlet). Các phiên bản, starter bổ sung hoặc cấu hình do ứng dụng tạo ra có thể thay đổi kết quả; không coi những biểu hiện dưới đây là bất biến cho mọi dự án Spring.

## 2. Phân biệt hai lớp “mặc định” quan trọng

Mặc dù đều xuất hiện sau khi thêm starter, **bảo mật request HTTP** và **nguồn tài khoản đăng nhập** là hai quyết định cấu hình tự động có điều kiện riêng.

| Thành phần | Mục đích | Khi nào Boot thường cung cấp mặc định? |
| --- | --- | --- |
| Cấu hình web `SecurityFilterChain` | Quy định request nào cần xác thực; bật form login và HTTP Basic | Khi ứng dụng Servlet không tự cung cấp bean `SecurityFilterChain` thay thế mặc định của Boot |
| `UserDetailsService` trong bộ nhớ | Cung cấp một người dùng để thử xác thực | Khi Boot không thấy các bean xác thực do ứng dụng khai báo thuộc các loại khiến cấu hình user mặc định phải nhường quyền, ví dụ `UserDetailsService`, `AuthenticationProvider`, `AuthenticationManager` hoặc cơ chế tương ứng |

**Hệ quả:** thêm bean `SecurityFilterChain` tùy chỉnh khiến cấu hình HTTP mặc định của Boot lùi lại, nhưng **không mặc nhiên loại bỏ** tài khoản `user`. Ngược lại, cung cấp `UserDetailsService` riêng làm thay đổi nguồn tài khoản mà không tự động tắt chính sách yêu cầu xác thực mọi request. Phải kiểm tra riêng **cấu hình filter chain** và **nguồn authentication**.

Khi không có cấu hình web riêng, cấu trúc ý tưởng của Boot tương đương:

```java
// Minh họa logic mặc định, không phải file cần thêm vào ứng dụng.
http
    .authorizeHttpRequests(requests ->
        requests.anyRequest().authenticated())
    .formLogin(Customizer.withDefaults())
    .httpBasic(Customizer.withDefaults());
```

Đây là **phần minh họa cấu hình**, chưa phải một lớp Java độc lập; nó cho thấy ba ý chính: mọi request còn thuộc phạm vi bảo vệ phải được xác thực, hỗ trợ trang/form login và hỗ trợ HTTP Basic. Spring Security vẫn có các quy tắc riêng để endpoint phục vụ đăng nhập hoạt động. Những chi tiết như CSRF, session, xử lý lỗi và lựa chọn điểm bắt đầu xác thực vẫn do framework quản lý.

## 3. Tài khoản `user` và mật khẩu sinh tự động

### 3.1. Mật khẩu đến từ đâu?

Trong tình huống sử dụng user mặc định, Spring Boot tạo một người dùng trong bộ nhớ, thường với:

- **Username:** `user`.
- **Password:** chuỗi ngẫu nhiên được sinh khi khởi động, được hiển thị trong log khởi động nếu logger phù hợp đang cho phép thông báo.
- **Role:** `USER` (tương ứng với authority `ROLE_USER` trong quy ước role của Spring Security).

Log thường có thông báo **“Using generated security password”** kèm giá trị thực tế, cùng lời nhắc chỉ sử dụng cơ chế này trong quá trình phát triển. Mật khẩu **không** phải password cố định lấy từ tài liệu và **không** được xem là giống nhau qua các lần khởi động lại. Nếu bạn không thấy thông báo, đừng tự đoán mật khẩu: có thể ứng dụng đã khai báo tài khoản hoặc provider riêng, đặt mật khẩu qua properties, thay cấu hình hoặc tắt/đổi mức log.

**Vì sao cần log?** Giá trị ngẫu nhiên chưa được người dùng chọn và chưa có giao diện tạo tài khoản, nên Boot cần một cách để người phát triển đăng nhập lần đầu. Nó là dữ liệu nhạy cảm: không chụp, sao chép lên issue công khai, đưa vào tài liệu hoặc chia sẻ log chứa mật khẩu này ra ngoài phạm vi phát triển.

### 3.2. User nằm ở đâu?

Trong trường hợp mặc định, Spring Boot tạo một `InMemoryUserDetailsManager` chứa tài khoản ấy. Nó **không** tạo bảng `users` trong database, không lưu mật khẩu vào một repository bền vững, không có luồng đăng ký tài khoản hay chức năng quên mật khẩu. Bản chất này giải thích tại sao cấu hình phù hợp để thử nhanh ứng dụng nhưng không đáp ứng quản trị danh tính thực tế.

Khi đổi mật khẩu qua properties, user vẫn có thể nằm trong bộ nhớ. **Đặt username/password cố định không tương đương với việc tích hợp database, LDAP, OAuth2/OIDC hoặc một identity provider.**

### 3.3. Phân biệt password sinh ngẫu nhiên và mã hóa password

Thông báo “mật khẩu sinh tự động” mô tả **nguồn và thời điểm tạo ra mật khẩu**. Nó không đồng nghĩa với JWT, access token, session ID hay một giao thức đăng nhập khác.

Mặt khác, Spring Security xác minh mật khẩu qua cơ chế `PasswordEncoder`/cấu hình xác thực phù hợp; không nên suy ra rằng một chuỗi hiển thị trong startup log là password hash cần nhập vào biểu mẫu. Người dùng nhập **giá trị mật khẩu gốc** đã được log sinh ra, còn ứng dụng có trách nhiệm kiểm chứng credential. Khi tự xây dựng nguồn người dùng production, phải chọn cơ chế lưu và mã hóa mật khẩu thích hợp.

## 4. Trang `/login` xuất hiện như thế nào?

Khi `formLogin` được bật và **chưa có trang đăng nhập tùy chỉnh**, Spring Security có thể dùng `DefaultLoginPageGeneratingFilter` để sinh một trang HTML đăng nhập. Nó nằm trong luồng **security filters**, vì vậy:

- Không cần `@GetMapping("/login")` để tạo trang mặc định.
- Không cần file template `login.html` hoặc frontend riêng chỉ để thử nghiệm.
- Trình duyệt truy cập `GET /login` sẽ được đưa tới form gồm username/password; khi POST form, framework xử lý xác thực theo cấu hình.
- Form mặc định có cơ chế tích hợp CSRF token khi CSRF protection hoạt động; việc tự tạo POST bằng tay phải quan tâm tới token theo cấu hình hiện tại.

Tên URL `/login` là mặc định thông thường của form login. Nếu bạn đổi `loginPage(...)`, `loginProcessingUrl(...)` hoặc thay `SecurityFilterChain` theo cách không bật form login, đừng mặc định trang HTML này vẫn xuất hiện.

### 4.1. Browser chưa đăng nhập

Một trình duyệt yêu cầu tài nguyên được bảo vệ, ví dụ `GET /hello` với `Accept: text/html`. Khi xác định chưa xác thực, Spring Security thường **redirect tới trang đăng nhập**. Trình duyệt theo chuyển hướng tới `/login` và hiển thị HTML được framework tạo.

Sau khi người dùng nhập `user` và mật khẩu đúng, Spring Security thực hiện xác thực, thiết lập ngữ cảnh bảo mật thích hợp và thường duy trì phiên đăng nhập qua **HTTP session/cookie** trong luồng form login. Sau xác thực thành công, nó có thể đưa người dùng trở về request đã bị chặn trước đó hoặc tới trang mặc định, tùy ngữ cảnh và cấu hình.

### 4.2. Client API / HTTP Basic chưa đăng nhập

Với client muốn HTTP Basic, server có thể trả **`401 Unauthorized`** và header `WWW-Authenticate: Basic ...` thay vì HTML redirect. Client gửi username/password bằng header `Authorization: Basic ...` trên request tiếp theo. Việc bật cả form login và HTTP Basic không buộc mọi client luôn nhận cùng một kiểu response: Spring Security sử dụng điểm bắt đầu xác thực phù hợp và có thể xét media type/`Accept`.

Lưu ý: **HTTP Basic chỉ mã hóa Base64 cặp username/password, không mã hóa đường truyền**. Chỉ gửi credential qua HTTPS trong môi trường thực tế; ví dụ `http://localhost` phía dưới chỉ dùng cục bộ để học.

### 4.3. Chuỗi xử lý khái niệm

```text
HTTP request
    |
    v
Servlet filter chain
    |
    v
Spring Security (DelegatingFilterProxy -> FilterChainProxy)
    |
    +-- Tài nguyên công khai phù hợp, ví dụ GET /login khi form login bật
    |       -> Security filter có thể sinh trang login
    |
    +-- Tài nguyên cần xác thực
            |
            +-- Chưa đăng nhập
            |       -> Browser HTML: thường redirect /login
            |       -> Basic/API: thường 401 challenge
            |
            +-- Đã đăng nhập
                    -> kiểm tra authorization
                    -> controller/servlet
```

Sơ đồ chỉ minh họa những nhánh chính, không phải danh sách chính xác tất cả filter. **`SecurityFilterChain`** của Spring Security biểu diễn bộ filter và matcher cho một request; **`jakarta.servlet.FilterChain`** là hợp đồng tiếp tục xử lý ở tầng servlet. Chúng liên hệ với nhau nhưng không phải cùng một kiểu.

## 5. Thực hành tối thiểu: ứng dụng Spring Boot có endpoint được bảo vệ

Ví dụ này có thể chạy độc lập với **JDK 17+, Gradle** và internet để tải dependency ở lần build đầu. Ta cố ý **không** khai báo `SecurityFilterChain`, `UserDetailsService`, `AuthenticationProvider` hoặc `spring.security.user.*` để quan sát mặc định thực sự.

Cấu trúc thư mục:

```text
security-default-demo/
├── build.gradle
├── settings.gradle
└── src/main/java/example/
    ├── DemoApplication.java
    └── HelloController.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'security-default-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

File `src/main/java/example/DemoApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

File `src/main/java/example/HelloController.java`:

```java
package example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello from protected endpoint";
    }
}
```

Dùng Gradle 8.x tương thích Spring Boot 3.3.x, ví dụ Gradle 8.5. Trong thư mục dự án, nếu đã có Gradle wrapper thì chạy `./gradlew bootRun` trên macOS/Linux hoặc `.\gradlew.bat bootRun` trên PowerShell Windows. Nếu chỉ có các file trong sơ đồ và đã cài Gradle phù hợp, dùng lệnh:

```bash
gradle bootRun
```

**Quan sát lúc khởi động:** ứng dụng thường ghi mật khẩu được sinh tự động vào log. Hãy đọc giá trị ngay trong terminal đang chạy và giữ kín. Đừng chép password vào file mã nguồn để test. Vì mật khẩu là ngẫu nhiên và log có timestamp/port tùy môi trường, tài liệu **không đưa ra stdout giả định là chính xác**.

### 5.1. Thử luồng trình duyệt

1. Mở `http://localhost:8080/hello` trong một phiên trình duyệt chưa đăng nhập. Với luồng HTML, trình duyệt thường được điều hướng đến `http://localhost:8080/login`.
2. Tại form đăng nhập mặc định, nhập tên `user` và mật khẩu được ghi trong terminal khởi động.
3. Đăng nhập thành công rồi truy cập lại `/hello`. Body HTTP là văn bản:

```text
Hello from protected endpoint
```

Nếu trình duyệt chuyển đến đường dẫn `/` sau đăng nhập trong khi ví dụ chỉ có `/hello`, bạn có thể thấy **404** ở `/` dù xác thực đã thành công. Hãy mở lại `/hello` để kiểm tra endpoint; đừng kết luận 404 luôn là lỗi password.

### 5.2. Thử HTTP Basic với curl

Trên terminal khác, thử request thường:

```bash
curl -i -H "Accept: application/json" http://localhost:8080/hello
```

Với cơ chế mặc định này, client yêu cầu JSON và chưa xác thực thường nhận `401 Unauthorized`; header và body cụ thể có thể thay đổi theo cách framework chọn entry point. Nếu yêu cầu HTML, kết quả có thể là `302 Found` với `Location: .../login`.

Tiếp theo, gửi credential bằng HTTP Basic. Dùng `--user user` **không kèm dấu hai chấm và mật khẩu** để curl hỏi password tương tác, tránh ghi credential vào lệnh:

```bash
curl -i --user user http://localhost:8080/hello
```

Khi curl hỏi mật khẩu, nhập giá trị sinh trong log khởi động. Khi xác thực thành công, phản hồi thường có `HTTP 200` và body:

```text
Hello from protected endpoint
```

**PowerShell Windows:** dùng `curl.exe` thay cho `curl` nếu môi trường có alias PowerShell khác với chương trình curl thật:

```powershell
curl.exe -i --user user http://localhost:8080/hello
```

Không sử dụng mật khẩu đang tồn tại trong production để chạy thử trên kết nối HTTP thường. Mục đích bài này là quan sát khả năng bảo vệ request mặc định ở `localhost`.

### 5.3. Vì sao không cần viết security config?

Phụ thuộc `spring-boot-starter-security` kích hoạt hệ sinh thái cấu hình tự động phù hợp. Spring Security đưa filter bảo mật vào Servlet filter chain; Spring Boot cung cấp default web chain và default in-memory user **khi điều kiện áp dụng còn đúng**.

Controller chỉ biết trả nội dung khi được gọi. Việc chuyển hướng, challenge Basic hay chặn request xảy ra **trước khi controller xử lý**, không phải do `@GetMapping` tự kiểm tra password.

## 6. Đổi tên hoặc mật khẩu bằng properties: tác động thật sự

Spring Boot có các properties thường dùng cho **user mặc định**:

```properties
spring.security.user.name=learner
spring.security.user.password=local-demo-password
spring.security.user.roles=USER
```

Trong ứng dụng không có nguồn user riêng, cấu hình trên khiến người dùng mặc định có tên `learner` với mật khẩu đã cấu hình. Do đó Boot **không cần sinh mật khẩu ngẫu nhiên** cho cùng cấu hình này, và thông báo “Using generated security password” có thể không còn. `roles=USER` là role mặc định phổ biến; liệt kê ở đây để minh họa thuộc tính.

**Chỉ dùng giá trị trên cho môi trường học tập cục bộ.** Trong dự án thật, không commit plaintext password vào repository, không ghi nó vào log hoặc tài liệu và không sử dụng một tài khoản chung cho mọi người. Nếu thực sự cần secret cấu hình, dùng cơ chế quản lý secret / cấu hình môi trường thích hợp. Để quản trị người dùng thật, cung cấp `UserDetailsService`, authentication provider hoặc giải pháp identity tương ứng với yêu cầu hệ thống.

**Phân biệt hành vi:**

- Đổi `spring.security.user.name` / `password` làm thay đổi credential của **user mặc định**; nó không tự tạo chính sách phân quyền mới.
- Thêm `UserDetailsService` tự triển khai làm Boot nhường cơ chế user mặc định; các properties trên không buộc provider khác dùng chúng.
- Thêm một `SecurityFilterChain` có thể thay đổi URL nào cần bảo vệ hoặc cách đăng nhập; không mặc định loại bỏ user in-memory nếu chưa cấu hình nguồn xác thực riêng.
- Xóa `spring-boot-starter-security` hoặc thay đổi auto-configuration không phải cách đúng để định nghĩa một chính sách bảo mật chủ động cho ứng dụng production.

## 7. Khi tự khai báo `SecurityFilterChain`, điều gì đổi?

Giả sử cần thêm một endpoint công khai. Lúc đó ứng dụng có thể tự khai báo security filter chain. File sau là **cấu hình thay thế tùy chọn**, không xuất hiện trong ứng dụng ở mục 5; muốn chạy riêng, hãy thêm file `src/main/java/example/WebSecurityConfig.java` vào dự án:

```java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain appSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated());

        http.formLogin(Customizer.withDefaults());
        http.httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Ví dụ chỉ cấu hình chính sách bảo vệ; nếu muốn endpoint `/public` trả dữ liệu, ứng dụng vẫn cần controller/mapping tương ứng. `requestMatchers("/public").permitAll()` **không tự tạo endpoint**.

Khi bean `SecurityFilterChain` do ứng dụng cung cấp, default **web security chain của Boot** nhường quyền. Trong lớp trên, ta **chủ động bật lại** `formLogin` và `httpBasic` để tiếp tục có hai cơ chế tương ứng; nếu bỏ `formLogin(...)`, đừng mong trang đăng nhập mặc định vẫn được tạo ra chỉ vì dependency Security đang có mặt.

Cấu hình này **không khai báo `UserDetailsService`**, nên Boot vẫn có thể cung cấp `user` và mật khẩu sinh tự động theo những điều kiện liên quan đến xác thực. Đây là ví dụ trực tiếp cho sự độc lập giữa **chain HTTP** và **user store**.

## 8. CSRF, session và phân biệt các mã phản hồi

### 8.1. CSRF bật mặc định có ảnh hưởng gì?

Với ứng dụng Servlet thông thường dùng Spring Security, cơ chế **CSRF protection** được bật mặc định. Những HTTP method mang ý nghĩa thay đổi trạng thái, chẳng hạn `POST`, `PUT`, `PATCH` hoặc `DELETE`, thường cần CSRF token hợp lệ nếu không thuộc trường hợp được bỏ qua có chủ đích.

- Form login do Spring Security sinh có khả năng mang trường token phù hợp với cấu hình CSRF.
- Gửi `POST /login` bằng `curl` mà thiếu CSRF token/cookie tương ứng có thể nhận **403 Forbidden** trước cả khi xác thực mật khẩu.
- Gửi API `POST` không có CSRF token cũng có thể nhận 403; điều đó không chứng minh username/password sai.
- Không nên tắt CSRF toàn ứng dụng chỉ để làm một ví dụ `POST` hoạt động; cần hiểu mô hình session, cookie và nguy cơ CSRF trước khi chọn cấu hình.

Trong ví dụ `GET /hello`, việc quan sát Basic authentication tránh phải xử lý CSRF token và giúp tập trung vào hành vi mặc định.

### 8.2. Form login thường gắn với session

Khi xác thực bằng form login, Spring Security có thể lưu trạng thái đăng nhập gắn với HTTP session để người dùng không phải nhập password ở mỗi request. Browser gửi cookie phiên (thường là `JSESSIONID` trong ứng dụng Servlet), và ứng dụng tải ngữ cảnh bảo mật ở những request tiếp theo theo cấu hình security context.

HTTP Basic thường gửi credential trong **mỗi request** và không đồng nghĩa với cơ chế session login. Nhưng đừng mặc nhiên coi mọi cấu hình hỗ trợ Basic đều hoàn toàn stateless: điều đó còn phụ thuộc `SessionCreationPolicy` và cách ứng dụng quản lý ngữ cảnh.

### 8.3. Bảng đọc nhanh khi thử nghiệm

| Thử nghiệm | Kết quả thường gặp với cấu hình mặc định | Điểm cần hiểu |
| --- | --- | --- |
| `GET /login` qua browser | HTTP 200 và form HTML | Trang do Security sinh nếu form login bật, chưa có login page tùy chỉnh |
| `GET /hello`, chưa đăng nhập, ưu tiên HTML | Redirect `302` về `/login` | Chưa được xác thực; browser theo redirect |
| `GET /hello`, chưa đăng nhập, client API phù hợp | HTTP `401`, thường kèm Basic challenge | Khác với redirect HTML vì lựa chọn entry point |
| `GET /hello`, credential Basic đúng | HTTP `200`, body `Hello from protected endpoint` | Filter cho request đi tới controller |
| `GET /hello`, credential Basic sai | HTTP `401` hoặc xử lý tương đương theo entry point | Xác thực thất bại; không phải “controller hỏng” |
| `POST` thay đổi trạng thái, thiếu CSRF token | Thường `403` | CSRF có thể chặn trước logic controller |

Đây là những **hành vi thường gặp**, không phải snapshot bảo đảm cho mọi header, cookie, redirect URL hay status trong mọi bản cấu hình. Muốn kết luận một trường hợp thực tế, hãy ghi lại request method, URL, `Accept`, trạng thái cookie, security config và log.

## 9. Lỗi thường gặp và cách chẩn đoán theo nguyên nhân

**1. “Đã thêm Security starter mà mọi endpoint đều yêu cầu đăng nhập.”** Đây thường chính là chính sách mặc định `anyRequest().authenticated()`. Hãy kiểm tra có cấu hình `SecurityFilterChain` riêng không và có cần khai báo public endpoint nào không. Không nên tắt toàn bộ bảo mật chỉ vì cần một health/public endpoint.

**2. “Không tìm thấy mật khẩu sinh ra trong log.”** Kiểm tra startup log đầy đủ, logger, việc khai báo `spring.security.user.password` và các authentication bean như `UserDetailsService` / `AuthenticationProvider`. Nếu nguồn xác thực do ứng dụng cung cấp, có thể không tồn tại generated password mặc định để tìm.

**3. “Tại sao login page vẫn có dù không có controller `/login`?”** Trang có thể do `DefaultLoginPageGeneratingFilter` sinh và trả về trong filter chain. Đó là hành vi framework, không phải Spring MVC tự phát hiện một file view.

**4. “Truy cập `/login` 404 hoặc không có form.”** Xem có tự tạo `SecurityFilterChain` mà quên `formLogin(...)`, có thay login page/login URL không, có cấu hình chỉ sử dụng HTTP Basic hay OAuth2/resource server không. Không nên đoán mọi ứng dụng có starter Security đều dùng form login.

**5. “Trình duyệt chuyển hướng `302` nhưng curl lại nhận `401`.”** Có thể đúng vì framework phân biệt tương tác HTML và client API. So sánh `Accept`, `Content-Type`, cookie, trạng thái đăng nhập và header `WWW-Authenticate`; không coi hai response khác nhau là mâu thuẫn.

**6. “Đăng nhập đúng mà POST vẫn `403`.”** Kiểm tra CSRF token và session/cookie tương ứng, đặc biệt khi gửi POST thủ công hoặc bằng API client. HTTP `403` không đồng nghĩa mật khẩu sai; xét security filter quyết định response.

**7. “Đổi SecurityFilterChain rồi vẫn thấy user mặc định.”** Vì mặc định web chain và mặc định user service do các auto-configuration khác nhau quyết định. Muốn thay user store, định nghĩa nguồn xác thực phù hợp.

**8. “Đã đăng nhập nhưng truy cập `/` bị 404.”** Có thể ứng dụng chưa ánh xạ `/`. 404 là lỗi không tìm thấy route, khác 401/403; truy cập đúng endpoint và kiểm tra redirect saved request.

**9. “Mật khẩu cũ không còn dùng được sau restart.”** Nếu đang dùng generated password mới mỗi lần khởi động, hành vi này là dễ hiểu. Không nên lưu hoặc dùng lại password của lần chạy trước như một thông tin ổn định.

**10. “Muốn dùng default user cho production.”** Đây là phương án học tập, thiếu quản lý vòng đời tài khoản, thay đổi mật khẩu an toàn, chính sách truy cập thực tế và các cơ chế quản trị khác. Hãy thiết kế authentication/authorization rõ ràng cho môi trường đích.

## 10. Quy trình kiểm tra nhanh khi bắt đầu module Servlet Security

1. Kiểm tra ứng dụng thật sự có `spring-boot-starter-security` và đang chạy theo stack **Servlet**, không phải nhầm với Spring WebFlux.
2. Xem có bean `SecurityFilterChain` riêng hay cấu hình bảo mật từ thư viện khác không; nếu có, default web behavior có thể đã thay đổi.
3. Xem có `UserDetailsService`, `AuthenticationProvider`, `AuthenticationManager` hoặc nguồn xác thực tùy chỉnh; nếu có, không mặc định dựa vào `user`.
4. Nếu user mặc định được tạo, lấy password từ log của **lần khởi động hiện tại**; không chép password vào Git hoặc chia sẻ terminal log.
5. Mở một endpoint đã biết tồn tại bằng browser chưa đăng nhập, rồi xem `/login`; so sánh với request `curl` có `Accept: application/json`.
6. Đăng nhập bằng `user` và password được log; xác minh endpoint có trả đúng nội dung sau xác thực.
7. Khi debug `401`/`302`/`403`/`404`, phân biệt **không xác thực**, **bắt đầu flow login**, **CSRF/authorization bị từ chối** và **không tìm thấy mapping**.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao chỉ thêm dependency Security mà controller `/hello` có thể đòi đăng nhập?

**Đáp án:** Boot tự cấu hình web `SecurityFilterChain` khi chưa có chain do ứng dụng cung cấp; mặc định yêu cầu xác thực HTTP request, kích hoạt form login và HTTP Basic.

**Câu 2.** Default username/password có lấy từ database không? Sau restart có chắc password cũ còn đúng không?

**Đáp án:** User mặc định thường nằm trong `InMemoryUserDetailsManager`, không phải database. Generated password có thể thay đổi khi ứng dụng khởi động lại, nên không được coi là credential cố định.

**Câu 3.** Có bắt buộc viết controller `@GetMapping("/login")` để nhìn thấy trang mặc định không?

**Đáp án:** Không. Khi form login bật và không có custom page, Spring Security có thể tự sinh trang qua security filter.

**Câu 4.** Tạo custom `SecurityFilterChain` thì tài khoản `user` chắc chắn biến mất đúng không?

**Đáp án:** Không. Web chain và nguồn user mặc định có những điều kiện lùi quyền riêng. Thay chain không tự động thay user store.

**Câu 5.** Vì sao `curl` trả `401` còn browser redirect `/login` cho cùng endpoint?

**Đáp án:** Spring Security có thể chọn authentication entry point dựa vào loại request và media type; HTTP Basic challenge và form login redirect đều là hành vi khởi đầu xác thực hợp lệ.

**Câu 6.** Khi POST login thủ công bị `403`, có thể kết luận mật khẩu đã nhập sai không?

**Đáp án:** Không. Trước hết kiểm tra CSRF token/cookie. CSRF có thể chặn request trước khi framework xử lý credential.

## 12. Ghi nhớ

- Default web security của Spring Boot Servlet thường là **authenticated requests + form login + HTTP Basic**, với điều kiện chưa có `SecurityFilterChain` thay thế.
- Default authentication user thường có **username `user`, role `USER` và generated password xuất hiện trong startup log**, với điều kiện chưa bị cấu hình tài khoản/provider riêng thay thế.
- **`/login` có thể do filter sinh ra**; không cần tự viết view/controller trong ví dụ mặc định.
- Browser HTML có thể nhận redirect, API client có thể nhận HTTP Basic challenge; **302, 401, 403, 404** cần được phân biệt theo ngữ cảnh.
- Đặt `spring.security.user.*` giúp thử nghiệm cục bộ; cấu hình production cần nguồn tài khoản, lưu giữ credential và chính sách truy cập được thiết kế phù hợp.

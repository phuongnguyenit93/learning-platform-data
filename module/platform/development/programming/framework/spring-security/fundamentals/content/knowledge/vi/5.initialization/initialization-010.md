# Thử nghiệm bằng trình duyệt, curl và bộ kiểm thử trước khi mở rộng cấu hình

> **Mục tiêu của buổi thực hành:** Trước khi tự viết hàng loạt `SecurityFilterChain`, JWT filter hoặc các rule phân quyền, hãy **quan sát đúng hành vi Spring Security đang cung cấp**, ghi lại kỳ vọng và xây bộ kiểm thử tái chạy được. Dùng **trình duyệt** để hiểu login/session/cookie, **curl** để nhìn rõ HTTP status/header, và **MockMvc + Spring Security Test** để kiểm tra trường hợp cho phép lẫn từ chối. Sau khi có đường chuẩn, thay đổi từng phần nhỏ và kiểm tra lại ngay.

Bài thuộc nhóm **Khởi tạo** của module **Spring Security – fundamentals**. Trọng tâm là **ứng dụng Spring Boot 3.x dùng Spring MVC/Servlet và cấu hình Spring Security mặc định**, trước khi mở rộng. Với WebFlux cần bộ kiểm thử WebTestClient và `SecurityWebFilterChain` tương ứng; không áp dụng nguyên xi toàn bộ code Servlet.

## 1. Kết quả học tập

Sau bài, bạn có thể:

1. Chạy ứng dụng có `spring-boot-starter-security` nhưng **chưa tự khai báo** `SecurityFilterChain`; nhận diện tài khoản `user` và mật khẩu phát sinh ở log dành cho development.
2. Phân biệt hành vi browser muốn HTML (thường redirect đến `/login`) với client muốn JSON (thường nhận `401 Unauthorized`), khi cùng gọi endpoint bảo vệ.
3. Sử dụng `curl -i`, `-H "Accept: application/json"` và `-u user` để quan sát status, `Location`, `WWW-Authenticate`, cookie và response body.
4. Chứng minh `401` (chưa xác thực), `403` (thiếu quyền hoặc CSRF), `200` (được phép) và `302` (redirect login) khác nhau; không chỉ dựa vào “màn hình hiện chữ gì”.
5. Viết tích hợp test bằng `@SpringBootTest`, `@AutoConfigureMockMvc`, `@WithMockUser`/`user()` và `csrf()`; hiểu mock user kiểm thử quyền, **không kiểm chứng password thật**.
6. Phân biệt một lỗi do security filter chặn với lỗi định tuyến hoặc lỗi nghiệp vụ.
7. Thêm một cấu hình truy cập đầu tiên, có phạm vi rõ ràng và kiểm thử lại các hành vi cũ ngay sau thay đổi.

## 2. Tại sao phải đo mặc định trước?

Người mới thường gặp hiện tượng: vừa thêm dependency Spring Security, mọi URL đều đòi đăng nhập. Họ lập tức thêm `.anyRequest().permitAll()` hoặc `.csrf(csrf -> csrf.disable())` để API “chạy lại”. Làm vậy che mất câu hỏi quan trọng: **điều gì đang bảo vệ request và điều gì thực sự cần thay đổi?**

Trong ứng dụng Spring Boot 3.5 với Spring MVC và starter security, nếu bạn chưa tự cấu hình các thành phần security chính, Spring Boot có thể tạo sẵn:

- Một `SecurityFilterChain` mặc định bảo vệ các endpoint bằng authentication.
- Một user in-memory có username `user` và **mật khẩu ngẫu nhiên**, được in ra log khi khởi động (chỉ dùng development; yêu cầu logging thích hợp để nhìn thấy).
- Cơ chế form login trên trình duyệt và HTTP Basic trên client thích hợp, thông qua phân biệt request/content negotiation.
- Chống CSRF trên những request HTTP cần bảo vệ, security headers mặc định và cơ chế quản lý security context/session tương ứng.

Đây là **đường khởi tạo học tập**, không phải thiết kế user/role/token cho production. Việc Spring Security hoạt động ở HTTP boundary không đồng nghĩa tự bảo vệ từng resource, SQL query hay business operation.

**Nguyên tắc thí nghiệm:** Đừng chỉ hỏi “được truy cập không?”. Hãy hỏi:

1. Request đi qua URL nào, HTTP method gì, có `Accept` và `Content-Type` nào?
2. Có credential hợp lệ không? Browser có đang giữ session cookie từ lượt trước không?
3. Status thực sự là bao nhiêu? Header `Location`, `WWW-Authenticate`, `Set-Cookie` phản ánh điều gì?
4. Security chặn request trước controller, hay request đã qua security nhưng controller trả lỗi?
5. Kết quả có tái lập được khi dùng cửa sổ ẩn danh hoặc chạy lại test không?

## 3. Ba lớp quan sát: browser, curl, test

| Công cụ | Nên dùng để tìm hiểu | Hạn chế cần biết |
| --- | --- | --- |
| **Trình duyệt** | Trang login, redirect, session cookie, form CSRF hidden field, hành vi tải tài nguyên | Browser tự quản cookie, redirect, cache; dễ che mất request gốc |
| **curl** | Raw status/header/body, Basic auth, `Accept`, redirect, cookie jar, CSRF lỗi | Không tự tái tạo session/trang form và JavaScript của browser nếu không mô phỏng |
| **MockMvc + Spring Security Test** | Test tự động rule HTTP, principal, status, CSRF, regression | Thường chạy không mở HTTP socket; không chứng minh TLS/reverse proxy hoặc credential production đã đúng |

Ba công cụ bổ sung cho nhau. Một test MockMvc thành công không chứng minh cấu hình HTTPS production đúng; một lần đăng nhập thành công bằng browser không chứng minh POST đã có CSRF protection; và `curl -k` dùng được với chứng thư sai không phải bằng chứng transport an toàn.

## 4. Chuẩn bị môi trường

Ví dụ sử dụng **JDK 17+**, Maven 3.6.3+ và **Spring Boot 3.5.16**. Bản 3.5.16 đã được phát hành ngày 25/06/2026 và là bản OSS cuối dòng 3.5; chọn dòng Boot 4.x đang được hỗ trợ, cùng bản vá mới, khi triển khai một dự án production mới. Khóa version ở đây nhằm giữ cú pháp demo nhất quán với Spring Security 6.5.x và Spring Boot 3.5.

Kiểm tra môi trường tại terminal:

```bash
java -version
mvn -version
```

Kỳ vọng: Java hiển thị **17 hoặc cao hơn**, Maven hiển thị version và JDK đang sử dụng. Đừng dựa vào một bản sao nguyên văn của stdout vì máy, vendor JDK và Maven version khác nhau.

Cấu trúc dự án tối thiểu:

```text
security-baseline-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/baseline/BaselineApplication.java
    └── test/
        └── java/demo/baseline/BaselineSecurityTests.java
```

**Chưa tạo class `SecurityConfig`, `SecurityFilterChain`, custom authentication provider hoặc JWT filter ở bước đầu.** Mục tiêu là đo hành vi của bản khởi tạo.

### 4.1. Tạo pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>security-baseline-demo</artifactId>
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

Hai starter đầu tiên chạy web + security. Hai dependency `test` bổ sung JUnit/MockMvc và helper bảo mật dùng trong test. Không khai báo `spring-boot-starter-webflux` trong demo Servlet này.

### 4.2. Mã ứng dụng hoàn chỉnh, không có SecurityConfig

Tạo `src/main/java/demo/baseline/BaselineApplication.java`:

```java
package demo.baseline;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BaselineApplication {
    public static void main(String[] args) {
        SpringApplication.run(BaselineApplication.class, args);
    }
}

@RestController
class DemoController {

    @GetMapping("/hello")
    String hello(Authentication authentication) {
        return "Hello " + authentication.getName();
    }

    @GetMapping("/health")
    String health() {
        return "ok";
    }

    @GetMapping("/admin")
    String admin() {
        return "admin-action";
    }

    @PostMapping("/notes")
    String createNote(Authentication authentication) {
        // Chỉ minh họa request POST; không có side effect hay database.
        return "created-by-" + authentication.getName();
    }
}
```

Bốn route được tạo **để có đích thử nghiệm**, không vì chúng đã được bảo vệ khác nhau. Ở cấu hình security mặc định, kể cả `/health` hay `/admin` cũng không tự động công khai hay yêu cầu role riêng chỉ vì tên URL. Điều gì được phép lúc này phụ thuộc vào chính sách **mặc định**, không phụ thuộc tên method controller.

**Điểm quan trọng:** `Authentication authentication` được Spring MVC cung cấp khi request đã được xác thực. Việc controller có thể nhận tham số này không tự tạo ra bước xác thực; bộ filter của Spring Security làm việc trước controller.

### 4.3. Khởi động ứng dụng

```bash
mvn spring-boot:run
```

Nếu chạy thành công, ứng dụng thường lắng nghe `http://localhost:8080` theo cấu hình mặc định. Trong log của quá trình khởi động, tìm dòng bắt đầu bằng:

```text
Using generated security password:
```

Phần sau dấu hai chấm là mật khẩu **ngẫu nhiên của lượt chạy này**, không phải một chuỗi cố định trong tài liệu. Username mặc định là `user`. Log này chỉ tồn tại khi Boot thực sự đang tạo user mặc định; nếu bạn cung cấp `UserDetailsService`, `AuthenticationProvider`, auth module khác hoặc cấu hình đã thay đổi, hiện tượng có thể khác.

**Giữ mật khẩu trong terminal học tập; không gửi lên chat, Git, ảnh chụp, log CI công khai.** Mật khẩu sinh tự động không phải cách quản lý user production. Ở Spring Boot 3.5, dòng log thường ở mức WARN; nếu cấu hình logging quá hạn chế, có thể không thấy nó.

## 5. Thử bằng trình duyệt: nhìn luồng đăng nhập thật

### 5.1. Bắt đầu bằng một phiên ẩn danh

1. Mở cửa sổ private/incognito để không dùng lại cookie từ lần chạy trước.
2. Mở `http://localhost:8080/hello`.
3. Với request browser thích HTML, Spring Security thường trả redirect `302` tới trang `/login`. Trình duyệt tự theo redirect, nên thanh địa chỉ có thể chỉ hiển thị `/login`, làm người mới tưởng URL ban đầu không bị bảo vệ.
4. Trang login được Spring Security tạo khi cấu hình form login mặc định hoạt động.
5. Đăng nhập bằng username `user` và mật khẩu sinh trong log. Sau khi thành công, browser quay lại tài nguyên đã yêu cầu hoặc URL mặc định tùy cơ chế saved request.

Sau login, `GET /hello` phản hồi chuỗi:

```text
Hello user
```

Đây là **body thành công** của controller; status HTTP thường là `200`. Việc browser trả `Hello user` không có nghĩa mọi thao tác đều được phép, ví dụ POST còn có CSRF và sau này có thể thêm permission riêng.

### 5.2. Đọc Network thay vì chỉ nhìn màn hình

Mở Developer Tools → **Network**, bật **Preserve log** để giữ cả request khi trang redirect. Chọn từng request và kiểm tra:

| Request | Điều cần quan sát |
| --- | --- |
| `GET /hello` lần đầu (ẩn danh, Accept HTML) | Status `302` thường gặp; header `Location: /login` |
| `GET /login` | HTML form, status `200` nếu trang login hợp lệ |
| `POST /login` | Form gửi credential cùng CSRF token, có thể trả redirect sau xác thực |
| `GET /hello` sau login | Request gửi session cookie và nhận `200` |
| `POST /notes` từ form không có CSRF token | Bị `403` khi CSRF protection áp dụng |
| `GET /health` trong session còn đăng nhập | `200` do đã authenticated, không phải vì health public |

Ở tab **Application/Storage → Cookies**, bạn có thể thấy cookie session (tên phổ biến `JSESSIONID`), tùy phiên và thiết lập. **Không ghi hoặc chia sẻ giá trị cookie**: đó có thể là secret đủ để truy cập như user đang đăng nhập. Kiểm tra `HttpOnly`, `Secure`, `SameSite` theo môi trường; trong demo HTTP localhost, không dùng kết quả cookie flags làm chuẩn production.

**Bẫy:** Browser tự mang cookie cho request tiếp theo, nên nếu bạn đã login và reload `/hello` thì không tái hiện anonymous nữa. Hãy dùng private window mới hoặc xóa session theo cách an toàn khi cần so sánh. Một mã `200` trong phiên đã login không chứng minh endpoint công khai.

### 5.3. Vì sao thao tác logout cần cân nhắc CSRF?

Với form login và CSRF enabled, logout là thao tác thay đổi trạng thái. URL `GET /logout` có thể hiển thị trang xác nhận chứa form; thao tác POST thực sự thực hiện logout theo cơ chế tương ứng. Không suy ra rằng chỉ gọi GET /logout bằng curl sẽ luôn chấm dứt session; điều này phụ thuộc cấu hình logout/CSRF. Sau logout, hãy thử `GET /hello` để xác nhận đã trở lại trạng thái chưa xác thực.

## 6. Thử bằng curl: nhìn trực tiếp status, headers và Basic Auth

### 6.1. Lựa chọn cách gọi phù hợp

Các ví dụ dưới đây dành cho terminal ở cùng máy với server đang chạy. Trên Linux/macOS/Git Bash dùng `curl`; trên PowerShell có thể dùng `curl.exe` để tránh alias `curl` cũ. `-i` in cả response header và body; `-v` giúp xem trao đổi network chi tiết nhưng **có thể làm lộ credential/cookie** khi chia sẻ log.

**A. Client muốn JSON và chưa có credential:**

```bash
curl -i -H "Accept: application/json" http://localhost:8080/hello
```

Một phản hồi điển hình:

```http
HTTP/1.1 401
WWW-Authenticate: Basic realm="Realm"
```

Response body, các header phụ và định dạng status line có thể khác theo server/cấu hình. **Kết quả cần kiểm chứng là `401`**, không phải mọi byte của header; API client bị challenge thay vì redirect theo kiểu trình duyệt.

**B. Client muốn HTML và chưa có credential:**

```bash
curl -i -H "Accept: text/html" http://localhost:8080/hello
```

Kỳ vọng thường là `302` với header `Location` trỏ đến `/login`. Mặc định curl **không** tự theo redirect trừ khi dùng `-L`; vì vậy nó giúp nhìn thấy bước bị browser tự động che đi.

**C. Xác thực bằng HTTP Basic mà không đưa password lên command line:**

```bash
curl -i -u user -H "Accept: application/json" http://localhost:8080/hello
```

Curl sẽ hỏi password tương tác; nhập giá trị ngẫu nhiên từ log. Khi đúng, kỳ vọng status `200` và body:

```text
Hello user
```

Với password sai, kết quả dự kiến là không authenticated (thường `401`) và **không** nhận `Hello user`. Mã hóa Base64 của HTTP Basic **không** bảo vệ password trên mạng: chỉ dùng HTTP trên `localhost` cho lab; production phải dùng HTTPS.

**D. Một đường nghe có vẻ công khai vẫn bị bảo vệ:**

```bash
curl -i -H "Accept: application/json" http://localhost:8080/health
```

Ở baseline chưa có `permitAll`, `/health` cũng cần authentication; kỳ vọng `401`. Đây là dữ kiện để quyết định sau này mở đúng endpoint nào, không cần tắt hết bảo mật.

**E. Thử POST với user hợp lệ nhưng thiếu CSRF token:**

```bash
curl -i -u user -X POST http://localhost:8080/notes
```

Sau khi nhập password đúng, request **vẫn có thể nhận `403 Forbidden`** vì `CsrfFilter` yêu cầu token trên POST. Đó là một sự từ chối khác với `401` do thiếu/sai credential. CSRF filter trong Servlet thường kiểm tra trước filter xử lý Basic, nên lỗi 403 trên POST không tự chứng minh user được authenticate; để tách hai điều kiện cần test có cả credential và token hợp lệ.

**F. Quan sát riêng header mà không tự động theo redirect:**

```bash
curl -I -H "Accept: text/html" http://localhost:8080/hello
```

Lệnh `-I` gửi **HEAD** chứ không phải GET. Head và Get thường có xử lý tương tự về quyền, nhưng không hoàn toàn đồng nhất về handler/body; nếu muốn thử đúng GET và vẫn xem header, ưu tiên `curl -i` hoặc `curl -D - -o /dev/null` (trên POSIX). Đừng dùng `-I` để kết luận chính xác hành vi GET mà không nhận diện khác biệt HTTP method.

### 6.2. Hiểu ý nghĩa từng status

| Status | Nghĩa hữu ích trong lab | Không nên kết luận vội |
| --- | --- | --- |
| `200 OK` | Request đến được handler và trả kết quả thành công | Mọi endpoint, mọi user đều có quyền |
| `302 Found` | Chuyển hướng, thường sang trang login khi browser muốn HTML | Đây là “lỗi server” hoặc dữ liệu đã được trả |
| `401 Unauthorized` | Cần xác thực/credential không được chấp nhận, thường có challenge | Chỉ thiếu role; đây là trường hợp phân quyền 403 |
| `403 Forbidden` | Request bị từ chối, có thể do thiếu quyền **hoặc CSRF** | Đã xác thực thành công; CSRF có thể chặn sớm |
| `404 Not Found` | Không tìm thấy handler/tài nguyên hoặc policy chủ đích ẩn sự tồn tại | Spring Security đã/không chạy |
| `405 Method Not Allowed` | Path có handler nhưng method không hỗ trợ (tùy rule trước handler) | Một bằng chứng về phân quyền |
| `500 Internal Server Error` | Lỗi máy chủ | Cứ thêm `permitAll` là sửa được lỗi |

Mã response cuối cùng còn chịu tác động của security chain, controller, Spring MVC error handling, reverse proxy và bộ lọc khác. Test nên chỉ assert những trạng thái **được hợp đồng bài học bảo đảm**.

### 6.3. Khi cần mô phỏng phiên browser bằng curl

Đăng nhập qua form khác với Basic Auth. Với form login, cần quản lý:

1. Cookie jar được nhận ở `GET /login`.
2. CSRF token từ form/token repository và request tương ứng.
3. `POST /login` với đúng field username/password/token và cookie phiên.
4. Những request sau mang cookie đã cấp.

`curl -c cookies.txt` lưu cookie từ response và `curl -b cookies.txt` gửi lại cookie; **hai lệnh này không tự lấy hoặc thêm CSRF token**. Không sao chép token từ một session sang session khác rồi kỳ vọng hợp lệ.

Nếu chỉ cần xác minh baseline cơ bản, dùng browser cho session form và `curl -u` cho Basic; việc xây một script login form/CSRF riêng sẽ hợp lý hơn sau khi bạn đã hiểu bộ lọc và cách lưu token.

## 7. Viết bộ kiểm thử tự động đầu tiên với MockMvc

Browser/curl giúp khám phá. `mvn test` giúp biến phát hiện thành **quy tắc có thể chạy lại khi code thay đổi**.

### 7.1. Vì sao dùng @SpringBootTest + @AutoConfigureMockMvc?

- `@SpringBootTest` khởi động Spring application context với auto-configuration thật.
- `@AutoConfigureMockMvc` chuẩn bị `MockMvc` có thể chạy request qua Spring MVC và Spring Security filter chain.
- `spring-security-test` hỗ trợ `@WithMockUser`, `user()` và `csrf()`.
- Mỗi test làm rõ trạng thái mong đợi của một request, có thể chạy trong CI mà không mở browser.

Ví dụ dưới đây có thể biên dịch cùng `pom.xml` và `BaselineApplication.java` ở trên. Tạo `src/test/java/demo/baseline/BaselineSecurityTests.java`:

```java
package demo.baseline;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BaselineSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousHtmlRequestIsRedirectedToLogin() throws Exception {
        mvc.perform(get("/hello").accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));

        mvc.perform(get("/login").accept(MediaType.TEXT_HTML))
            .andExpect(status().isOk());
    }

    @Test
    void anonymousApiRequestGets401InsteadOfHello() throws Exception {
        mvc.perform(get("/hello").accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());

        // Route /health tồn tại, nhưng ở baseline vẫn yêu cầu login.
        mvc.perform(get("/health").accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice", roles = {"USER"})
    void authenticatedUserCanReadHello() throws Exception {
        mvc.perform(get("/hello"))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello alice"));

        // Trước khi có chính sách admin, baseline chỉ cần authenticated.
        mvc.perform(get("/admin"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-action"));
    }

    @Test
    void postNeedsCsrfEvenWhenUserIsPresent() throws Exception {
        mvc.perform(post("/notes").with(user("alice")))
            .andExpect(status().isForbidden());

        mvc.perform(post("/notes")
                .with(user("alice"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());

        mvc.perform(post("/notes")
                .with(user("alice"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created-by-alice"));
    }

    @Test
    void securityHeadersArePresent() throws Exception {
        mvc.perform(get("/login").accept(MediaType.TEXT_HTML))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"));
    }
}
```

Giải thích bài test:

- **Chặn anonymous:** request HTML có thể được đưa đến login, còn JSON client nhận `401`. Hai kết quả **không mâu thuẫn**, vì entry point được chọn dựa vào yêu cầu/client.
- **Mock user:** `@WithMockUser` hoặc `user("alice")` tạo `Authentication` giả lập. Alice **không cần tồn tại** trong `UserDetailsService` thật; test này kiểm tra việc filter, controller và policy hoạt động với identity, **không** kiểm tra rằng mật khẩu của Alice sẽ đăng nhập thành công.
- **CSRF:** `with(csrf())` thêm token hợp lệ trong request MockMvc; `with(csrf().useInvalidToken())` cố tình đưa token sai. Cả user đủ quyền mà thiếu token và user đủ quyền có token sai đều bị từ chối.
- **Headers:** `X-Content-Type-Options: nosniff` là một header phản hồi bảo vệ phổ biến trong Spring Security mặc định. Nếu bạn chạy qua proxy, kiểm tra thêm response ngoài thực tế; MockMvc không kiểm chứng hạ tầng production.

**Lưu ý về `@WithMockUser`:** test không chứng minh password/token validation. Muốn kiểm tra đường Basic authentication bằng test, dùng `httpBasic()` với một `UserDetailsService` test đã cấu hình; ở baseline ta cố ý để default password ngẫu nhiên nên kiểm thử mật khẩu bằng `curl -u user` và log local. Về sau, thêm test xác thực thật khi bạn bắt đầu định nghĩa identity provider.

### 7.2. Chạy và đánh giá

Dừng server dev nếu bạn muốn một môi trường sạch, sau đó tại thư mục dự án:

```bash
mvn test
```

Maven chạy JUnit và báo **BUILD SUCCESS** khi bộ kiểm thử đã thỏa kỳ vọng. Nếu thất bại, đọc **tên test và assertion cụ thể**, đừng xóa test hoặc tắt Spring Security chỉ để build xanh. Kiểm tra các nhóm vấn đề:

- Test HTML nhận `401` thay vì redirect: đã đặt `Accept: text/html` chưa; có cấu hình khác chiếm quyền form login không?
- Test JSON nhận redirect: kiểm tra content negotiation, entry point và session/cookie có từ request trước không.
- Test `POST /notes` có CSRF hợp lệ vẫn nhận `403`: đã thêm mock user không; security filter đã được gắn vào MockMvc chưa; rule URL khác có chặn không?
- Test `/admin` với Alice đột ngột chuyển sang 403: có cấu hình role mới được thêm trước khi hoàn thành baseline không?
- Test không tìm thấy `@WithMockUser`/`csrf()`: đã thêm `spring-security-test` ở scope `test` chưa?
- Có `NoClassDefFoundError` hoặc không tải được dependency: kiểm tra `java -version`, Maven local cache, dependency tree và BOM, **đừng trộn version Spring Security tùy ý**.

**Bộ test được trình bày như mã có thể chạy**, nhưng kết quả còn phụ thuộc môi trường JDK/Maven và dependency tương thích. Các status quan trọng được xác định dựa trên hành vi chuẩn của Spring Security 6.5 khi không có custom security configuration.

### 7.3. Test thành phần, integration test và bài test mạng thật

| Loại test | Phạm vi | Dùng khi nào? |
| --- | --- | --- |
| Unit test controller/service không có filter | Logic thuần | Validation, business rules; **không** xác minh HTTP security |
| MockMvc với Spring application context và filter | Servlet chain + controller | Test authentication/authorization/CSRF/headers |
| `@WithMockUser`/`user()` | Quyền với identity giả lập | Kiểm tra rule mà không phụ thuộc mật khẩu/token thật |
| `httpBasic()` + provider test thực | Basic credential end-to-end trong context | Kiểm tra authentication provider/encoder của app |
| Browser/curl kết nối server thật | HTTP headers, redirect, cookies, network | Kiểm tra setup thực tế và hành vi client |
| HTTPS/proxy integration test | TLS termination, headers, load balancer | Khi triển khai qua ingress/CDN/proxy |
| Database integration test | Owner/tenant/resource policy | Khi có dữ liệu và phân quyền nghiệp vụ |

Đừng viết nhiều unit test giả lập filter chain nhưng lại bỏ qua một integration test thật: lỗi matcher, thứ tự filter, session và CSRF thường chỉ lộ khi chạy qua Spring Security.

## 8. Viết bảng kiểm chứng trước khi chỉnh cấu hình

Ghi kết quả quan sát được, để sau này phát hiện regression. Ví dụ ma trận cho **baseline** ở mục 4:

| # | Client, method, path | Credentials/CSRF | Kỳ vọng ban đầu | Cách quan sát |
| --- | --- | --- | --- | --- |
| 1 | Browser `GET /hello` | Không | Redirect login (thường 302) | Network tab |
| 2 | curl `GET /hello`, `Accept: application/json` | Không | `401` | `curl -i` |
| 3 | curl `GET /hello` | Basic hợp lệ | `200`, `Hello user` | `curl -u user` |
| 4 | curl `GET /hello` | Basic sai | Không được `Hello user`, thường `401` | `curl -u user` |
| 5 | Browser `GET /login` | Không | Login form `200` | Browser/MockMvc |
| 6 | curl `GET /health`, JSON | Không | `401`, dù tên là “health” | curl/MockMvc |
| 7 | MockMvc `GET /admin` | Alice mock user | `200` ở baseline: chưa có rule role riêng | `@WithMockUser` |
| 8 | MockMvc `POST /notes` | Alice, không CSRF | `403` | `user()` |
| 9 | MockMvc `POST /notes` | Alice, CSRF sai | `403` | `csrf().useInvalidToken()` |
| 10 | MockMvc `POST /notes` | Alice, CSRF đúng | `200`, body `created-by-alice` | `csrf()` |

Khi test hoặc browser/curl cho kết quả khác, xác định nguyên nhân cụ thể trước khi ghi rằng default Spring Security “không hoạt động”. Ví dụ request đã nhận cookie session, app có file `application.properties` cung cấp `spring.security.user.*`, một starter OAuth2 khác nằm trên classpath, hay một security chain đã được định nghĩa ở nơi khác.

### 8.1. Kiểm tra có thực sự đang dùng mặc định không

Trong lab ban đầu:

- Có đúng dependency `spring-boot-starter-security` không?
- Có bean `SecurityFilterChain` đã được dự án, thư viện hay auto-configuration bổ sung khác khai báo không?
- Có bean `UserDetailsService`, `AuthenticationProvider` hoặc `AuthenticationManager` tùy chỉnh không?
- Có spring profile, environment variable hoặc test configuration thay đổi `spring.security.user.name/password` không?
- Có starter OAuth2 Login/Resource Server/SAML thay đổi điều kiện auto-configuration không?
- Có session cookie sẵn trong trình duyệt hoặc gửi Basic credential tự động không?
- Mã 401/403 xuất phát từ Spring Security hay proxy bên ngoài?

Trong Spring Boot 3.5, **tự thêm bean `SecurityFilterChain` khiến Boot lùi khỏi default web security configuration**, nhưng **không mặc nhiên tắt** default `UserDetailsService`. Muốn thay danh tính hoặc phương thức xác thực, đó là quyết định riêng. Hiểu hai phạm vi này tránh lỗi “đã custom URL rule nhưng vẫn thấy user mặc định”.

## 9. Sau khi baseline xanh: thêm một thay đổi bảo mật nhỏ

Chỉ sau khi xác nhận bảng ở mục 8, ta thử yêu cầu thay đổi đầu tiên:

- `GET /health` được phép gọi **không đăng nhập**.
- `GET /admin` chỉ người có `ROLE_ADMIN` được vào.
- Các endpoint khác vẫn yêu cầu authenticated, giữ form login + HTTP Basic và CSRF protection.

Đây là **bản mở rộng có chủ đích**; không mở toàn bộ URL để giải quyết một endpoint cần public.

### 9.1. Thêm một bean SecurityFilterChain

Tạo `src/main/java/demo/baseline/WebSecurityRules.java`:

```java
package demo.baseline;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class WebSecurityRules {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Điểm cần đọc kỹ:

- `requestMatchers(HttpMethod.GET, "/health").permitAll()` chỉ cho phép GET của đường đó, không tự cho phép POST/DELETE hay các actuator endpoint khác.
- `requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")` yêu cầu authority `ROLE_ADMIN` theo quy ước prefix role mặc định.
- `anyRequest().authenticated()` tiếp tục buộc đăng nhập cho các đường còn lại; điều này **không** tự chặn hoàn toàn endpoint chưa có handler, vì sau bước authenticated Spring MVC còn quyết định 404/405.
- `formLogin(...)` và `httpBasic(...)` được khai báo rõ, vì khi ứng dụng tự tạo chain, bạn không nên giả định toàn bộ cấu hình web mặc định của Spring Boot vẫn được áp dụng nguyên trạng.
- Không có `csrf.disable()` nên CSRF protection vẫn được giữ theo cấu hình phù hợp cho Servlet form login.
- Không có `UserDetailsService` tự tạo, nên default user `user` có thể vẫn tồn tại. Đây vẫn chỉ là lab, không thể dùng làm cấu hình production.

Với nhiều chain trong tương lai, cần `securityMatcher(...)`/`@Order` và fallback rõ ràng. Ở bước khởi tạo này, **một chain match mọi request** giúp dễ quan sát và tránh để lộ URL ngoài phạm vi. Không cần chia nhiều chain khi chưa có nhu cầu.

### 9.2. Bổ sung kiểm thử cho chính sách mới

Sau khi thêm class `WebSecurityRules`, giữ lại các test về `/hello`, POST + CSRF và headers. **Thay/điều chỉnh** hai assertion baseline vốn kỳ vọng `/health` anonymous bị 401 và `/admin` với Alice được 200, vì chính sách chủ đích đã đổi. Cụ thể, trong `BaselineSecurityTests`, xóa kỳ vọng cũ cho hai endpoint này và thêm file sau.

Tạo `src/test/java/demo/baseline/FirstRulesTests.java`:

```java
package demo.baseline;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FirstRulesTests {

    @Autowired
    MockMvc mvc;

    @Test
    void healthIsTheOnlyNewPublicGetRoute() throws Exception {
        mvc.perform(get("/health").accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().string("ok"));

        mvc.perform(get("/hello").accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void adminRequiresAdminRole() throws Exception {
        mvc.perform(get("/admin").with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin").with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-action"));
    }

    @Test
    void existingAuthenticatedRouteStillWorks() throws Exception {
        mvc.perform(get("/hello").with(user("alice").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello alice"));
    }
}
```

**Chú ý trước khi chạy `mvn test`:** File `BaselineSecurityTests.java` chứa hai assertion chỉ đúng **trước khi mở rộng**, phải cập nhật chúng:

1. Trong `anonymousApiRequestGets401InsteadOfHello()`, bỏ đoạn `get("/health")` kỳ vọng `401`. Test `FirstRulesTests.healthIsTheOnlyNewPublicGetRoute()` nay kiểm tra nó trả `200`.
2. Trong `authenticatedUserCanReadHello()`, bỏ đoạn `get("/admin")` kỳ vọng `200` với Alice. Test `FirstRulesTests.adminRequiresAdminRole()` nay kiểm tra Alice `403`, admin `200`.

Giữ nguyên toàn bộ assertion cho `/hello`, `/login`, CSRF và header. Bằng cách đó, các case bất biến vẫn là **regression tests**, còn những case thay đổi được cập nhật theo chính sách có chủ đích. Nếu để hai kỳ vọng mâu thuẫn cùng tồn tại, suite sẽ đỏ ngay cả khi cấu hình mới đúng.

Sau khi chỉnh, chạy:

```bash
mvn test
```

Kỳ vọng là test thành công khi filter chain mới hoạt động đúng. Với user `user` mặc định (thường chỉ có `ROLE_USER`), browser/curl thật vào `/admin` vẫn không được phép; `user("admin").roles("ADMIN")` trong MockMvc **là principal giả lập**, không tự tạo tài khoản admin đăng nhập bằng password. Để kiểm tra authentication và admin role **đồng thời** bằng credential thật, cần cấu hình thêm user/provider test và test `httpBasic(...)`/login thực; đó là bước mở rộng tiếp theo.

### 9.3. Kiểm tra lại bằng browser và curl sau thay đổi

Mở lại server khi `mvn test` pass:

```bash
mvn spring-boot:run
```

Các lệnh kiểm chứng:

```bash
curl -i -H "Accept: application/json" http://localhost:8080/health
curl -i -H "Accept: application/json" http://localhost:8080/hello
curl -i -u user -H "Accept: application/json" http://localhost:8080/hello
curl -i -u user -H "Accept: application/json" http://localhost:8080/admin
```

Khi được curl hỏi, nhập mật khẩu user được sinh trong **lượt khởi động mới**. Kết quả kỳ vọng lần lượt:

| Request | Status | Giải thích |
| --- | --- | --- |
| `GET /health` anonymous | `200` | Rule mới `permitAll` |
| `GET /hello` anonymous JSON | `401` | `anyRequest().authenticated()` |
| `GET /hello` Basic user đúng | `200` | Được xác thực |
| `GET /admin` Basic user đúng | `403` | `ROLE_USER` không phải `ROLE_ADMIN` |

Trình duyệt mở `/health` không phải login; mở `/hello` ẩn danh vẫn đến form; mở `/admin` bằng default user đã login sẽ bị từ chối. Đây là cách kiểm chứng **before/after** theo mục tiêu, không cần thay đổi thêm hàng loạt thành phần cùng lúc.

## 10. CSRF, Cookie và thử POST cho đúng

### 10.1. Vì sao có Basic/password hợp lệ mà POST vẫn nhận 403?

CSRF là vấn đề request thay đổi trạng thái được trình duyệt tự gửi kèm credential có sẵn (cookie hoặc những dạng credential tự gửi khác). CSRF token giúp server xác nhận request đến từ luồng client được phép tương ứng. Spring Security Servlet thường bật CSRF protection theo mặc định khi dùng cấu hình phù hợp.

Trên lab này:

- `GET /hello` là thao tác đọc, CSRF token không cần cho request an toàn.
- `POST /notes` làm thay đổi trạng thái về mặt HTTP contract dù demo không ghi DB, nên CSRF protection chặn POST thiếu token.
- `with(csrf())` trong MockMvc cho phép test rõ sự khác biệt **có token hợp lệ** và **thiếu token**.
- `hasRole(...)` hoặc `authenticated()` không phải CSRF token. Có permission đúng không tự làm request chống được CSRF.

**Không dùng `csrf.disable()` chỉ vì curl POST bị `403`.** Một API thuần bearer token được script chủ động đặt header có mô hình rủi ro khác cookie auth; hãy đánh giá authentication và cookie thực tế trước khi loại trừ CSRF cho các endpoint xác định.

### 10.2. Form login trong browser

Form mặc định của Spring Security thường chứa hidden field `_csrf`; người dùng gửi form để framework xác minh. Nếu bạn viết form frontend tùy chỉnh, phải xử lý token đúng theo `CsrfTokenRepository` và request handler đã cấu hình. Với phiên dùng cookie, có thể cần gửi cả session cookie và token. Đừng lấy một token bất kỳ từ response hoặc một session khác rồi kết luận CSRF “không hoạt động” khi bị từ chối.

### 10.3. Kiểm tra cookies và session

Kiểm tra thuộc tính cookie như `HttpOnly`, `Secure`, `SameSite`, thời hạn và scope trong browser DevTools. Đừng đọc giá trị cookie ra log công khai. **HTTPS** mới bảo vệ credential/cookie trên mạng; các request HTTP từ lab chỉ dành cho `localhost`. Sau khi chuyển tới reverse proxy, cần test HSTS, forwarded headers, TLS termination và cookie flags theo kiến trúc thật.

## 11. Phân biệt lỗi Spring Security với lỗi của controller

Nếu kết quả không như mong đợi, theo các bước sau:

### 11.1. Đọc status trước khi sửa code

- `401` với `WWW-Authenticate`: request không được xác thực/challenge, kiểm tra credential hoặc Basic entry point.
- `302` và `Location: /login`: trình duyệt được đưa tới form login, không phải endpoint tự trả nội dung.
- `403` trên POST: kiểm tra **CSRF trước**, sau đó role/authority; đừng suy luận chỉ từ mã lỗi.
- `404`: endpoint có thể chưa được map hoặc một policy chọn che tài nguyên; kiểm tra security đã cho request đi tới handler chưa.
- `405`: method HTTP có thể không được controller xử lý; kiểm tra mapping, CSRF và rule theo method.
- `500`: exception trong server, xem log stack trace và lỗi nghiệp vụ thay vì tự động tắt filter.

### 11.2. Bật debug có kiểm soát

Trong **môi trường local** có thể đặt:

```properties
logging.level.org.springframework.security=DEBUG
```

Log khi khởi động/request có thể cho thấy các filter và đường đi security, nhưng nội dung/phạm vi khác nhau theo phiên bản. Không giữ mức TRACE/DEBUG quá rộng trên production và **không log** password, Basic Authorization, token, session cookie, các dữ liệu nhạy cảm. Với browser, kiểm tra DevTools Network để biết redirect nào xảy ra; với curl, dùng `-i` thay vì chia sẻ verbose log chứa credential.

### 11.3. Test quan hệ “request → chain → controller”

```text
Request /hello
  |
  v
Servlet FilterChain
  |
  v
Spring Security FilterChainProxy
  |
  +--> security context / authentication
  +--> CSRF (cho method cần kiểm tra)
  +--> authorization
  |
  +--> Bị chặn => 401, 302 hoặc 403 tùy tình huống
  |
  v
Spring MVC DispatcherServlet
  |
  v
@GetMapping / @PostMapping
  |
  v
Response body của controller
```

Bạn cần test cả **mặt bị từ chối** và **mặt được phép**. Nếu chỉ test `GET /hello` với mock user được `200`, chưa biết anonymous có bị chặn hay không. Nếu chỉ test anonymous bị 401, chưa biết valid user có thật sự vào được controller hay không.

## 12. Những sai lầm thường gặp khi mới học

### Sai lầm 1 — Không phân biệt redirect và lỗi authentication

**Triệu chứng:** Browser hiện login page, curl lại thấy 401, nên cho rằng bảo mật “không ổn định”.

**Giải thích:** Content negotiation và entry point của Spring Security có thể phân biệt request HTML/browser với service client. So sánh cùng URL và method nhưng có/không `Accept`, xem header `Location`/`WWW-Authenticate` để hiểu thay đổi.

### Sai lầm 2 — Đăng nhập rồi tưởng endpoint công khai

**Triệu chứng:** `/health` hiện `ok` trong browser, nhưng curl anonymous nhận 401.

**Giải thích:** Browser có session cookie. Kiểm tra bằng cửa sổ ẩn danh và curl không kèm credentials; trong lab baseline, `/health` không tự public.

### Sai lầm 3 — Lấy password trong tài liệu hoặc từ lần chạy cũ

**Triệu chứng:** `curl -u user` luôn nhận 401.

**Giải thích:** Password mặc định có thể sinh lại mỗi lần app khởi động. Dùng đúng giá trị trong log **phiên hiện tại**, không hard-code giá trị trong hướng dẫn hoặc CI. Khi app có custom user provider, behavior cũng có thể đổi.

### Sai lầm 4 — Bỏ qua CSRF để “chữa” 403

**Triệu chứng:** GET chạy, POST không chạy.

**Giải thích:** POST bị kiểm tra CSRF độc lập với việc có user hợp lệ. Dùng `MockMvc.with(csrf())` để chứng minh đường hợp lệ; với ứng dụng browser phải tích hợp token đúng.

### Sai lầm 5 — Dùng @WithMockUser rồi khẳng định password authentication đúng

**Triệu chứng:** Test xanh dù password encoder hoặc token verifier trong production bị lỗi.

**Giải thích:** Mock user được đưa thẳng vào SecurityContext test, không đi qua kiểm tra password thật. Viết thêm test `httpBasic()`/form login/provider/JWT decoding nếu sản phẩm cần bảo đảm đó.

### Sai lầm 6 — Viết hết security rules trong một lần

**Triệu chứng:** Sau khi thêm custom chain, không còn login form, lỗi 401 biến thành 403 hoặc endpoint ngoài `securityMatcher` bị lọt.

**Giải thích:** Bean `SecurityFilterChain` thay web auto-configuration mặc định của Boot; cần khai báo chính sách và cơ chế authentication mong muốn rõ ràng, có fallback match toàn request. Thêm rule theo từng mục tiêu rồi chạy lại regression suite.

### Sai lầm 7 — Test quá sát implementation

**Triệu chứng:** Test assert đúng số lượng filter, class nội bộ hoặc thứ tự log; nâng cấp bản vá nhỏ làm test đỏ dù hành vi vẫn đúng.

**Giải thích:** Với lab này, hợp đồng là **status, headers có ý nghĩa và response**, cùng đường từ chối/chấp nhận. Chỉ kiểm tra filter class cụ thể khi làm bài chuyên sâu về kiến trúc filter.

### Sai lầm 8 — Dùng curl -L rồi bỏ qua 302

**Triệu chứng:** Chỉ nhìn thấy trang login HTML với status cuối `200`; kết luận `GET /hello` trả 200 anonymous.

**Giải thích:** `-L` theo redirect; cần dùng `curl -i` không `-L` để thấy response đầu, hoặc bật `-v` trong môi trường an toàn và phân tích từng hop.

### Sai lầm 9 — Gửi dữ liệu nhạy cảm trong terminal hoặc report

**Triệu chứng:** Command chứa plaintext password/token trong history, chụp ảnh DevTools có cookie, gửi verbose log lên issue.

**Giải thích:** Dùng `curl -u user` để prompt password thay vì ghi password trực tiếp trong command line. Sanitize log/ảnh chụp và dùng dữ liệu mẫu.

### Sai lầm 10 — Chỉ thử một user một lần

**Triệu chứng:** Alice được xem dữ liệu của mình, nhưng có thể xem dữ liệu của Bob bằng cách đổi ID.

**Giải thích:** Ở baseline chỉ quan sát auth + CSRF. Khi bắt đầu có tài nguyên thật, thêm ma trận nhiều users/roles/tenant/owner và kiểm tra tại service/repository. `authenticated()` không tự bảo vệ object ownership.

## 13. Checklist trước khi mở rộng cấu hình

Hãy giữ lại kết quả từng bước dưới dạng test hoặc ghi chú kỹ thuật:

- [ ] Xác định app thật sự là Servlet/Spring MVC, dependency và Spring Boot version đang dùng.
- [ ] Đọc được dấu hiệu default security và generated user/password trong môi trường lab (hoặc giải thích rõ nếu đã thay auto-configuration).
- [ ] Browser private: `GET /hello` redirect login và sau đăng nhập hợp lệ trả nội dung đúng.
- [ ] Curl anonymous với JSON: `401`; curl Basic đúng: `200`; mật khẩu sai: bị từ chối.
- [ ] Nhìn thấy khác biệt `Accept: text/html` với `Accept: application/json`; không lẫn status từ redirect.
- [ ] POST khi thiếu/sai CSRF token bị chặn; POST có token hợp lệ và principal phù hợp được phép theo policy.
- [ ] MockMvc chạy được các case anonymous/authenticated, CSRF và header; test code không phụ thuộc password ngẫu nhiên.
- [ ] Biết việc `@WithMockUser` kiểm thử SecurityContext giả lập, chưa kiểm thử provider/credential thật.
- [ ] Có ma trận before/after nếu thêm `SecurityFilterChain`; biết quy tắc mới nào thay đổi kỳ vọng cũ.
- [ ] Giữ nguyên các regression tests không bị thay đổi khi thêm rule.
- [ ] Dùng HTTPS trong hệ thống thật; không lộ password/cookie/token trong log, history hoặc report.
- [ ] Chưa cấp quyền cho mọi endpoint bằng `permitAll`, chưa tắt CSRF chỉ để tránh lỗi test.
- [ ] Chuẩn bị thêm test owner/tenant/ACL khi ứng dụng có dữ liệu người dùng thực, không chỉ test truy cập URL.

## 14. Các câu hỏi tự kiểm tra

**Câu 1:** Trình duyệt vào `/hello` thấy trang login, nhưng curl gửi `Accept: application/json` nhận 401. Có phải Spring Security dùng hai luật phân quyền khác nhau?

**Trả lời:** Không nhất thiết. Cả hai đều yêu cầu xác thực. Entry point có thể chọn redirect form cho browser và HTTP Basic challenge cho service client. So sánh `Accept`, `Location` và `WWW-Authenticate`.

**Câu 2:** Bạn đã gọi `GET /health` thành công sau khi login. Có thể công bố `/health` public chưa?

**Trả lời:** Chưa. Phải thử request không credential/cookie; ở baseline Spring Boot, route này vẫn thường yêu cầu đăng nhập. Nếu sản phẩm quyết định cho public, thêm rule `permitAll` **cụ thể** và test nó.

**Câu 3:** Vì sao `POST /notes` với user/password đúng vẫn nhận 403?

**Trả lời:** CSRF protection áp dụng cho POST. Trong test, dùng `user(...)` và `csrf()` để kiểm chứng độc lập credential/permission và token; đừng vội tắt CSRF.

**Câu 4:** `@WithMockUser(username = "alice")` chứng minh Alice có thể đăng nhập bằng password thật không?

**Trả lời:** Không. Nó tạo authentication giả lập trong test. Muốn xác minh password, test provider/`httpBasic(...)`/form login với user test được cấu hình.

**Câu 5:** Thêm `SecurityFilterChain` làm mất trang login. Sửa thế nào?

**Trả lời:** Khi tự định nghĩa web security chain, khai báo lại những cơ chế cần dùng như `formLogin(Customizer.withDefaults())` và `httpBasic(Customizer.withDefaults())`, đồng thời định nghĩa authorization rules rõ ràng. Kiểm tra test redirect/401 sau thay đổi.

**Câu 6:** Sau khi thêm `hasRole("ADMIN")`, curl với default `user` bị 403. Có phải server bị lỗi?

**Trả lời:** Không. User mặc định không có `ROLE_ADMIN`. Test với mock admin xác nhận rule; nếu cần thử đăng nhập thật bằng role ADMIN thì cấu hình test identity/provider tương ứng và kiểm tra credential.

## 15. Ghi nhớ

1. **Thử mặc định trước khi mở rộng:** hiểu vì sao endpoint yêu cầu login, request JSON bị 401 và POST thiếu CSRF bị 403.
2. **Browser, curl và MockMvc trả lời ba câu hỏi khác nhau:** hành vi người dùng, giao thức HTTP thực, và tính lặp lại của hợp đồng bảo mật.
3. **Authentication, authorization và CSRF là những lớp kiểm tra khác nhau**; status lỗi phải được giải thích theo chuỗi xử lý.
4. **Mỗi thay đổi cấu hình phải có before/after test.** Khi chính sách thay đổi có chủ đích, cập nhật assertion tương ứng nhưng giữ test regression của phần không đổi.
5. **Bảo mật khởi tạo không phải bảo mật production.** Phải tiếp tục thiết kế identity provider, HTTPS, quyền trên tài nguyên, lifecycle token/session, kiểm thử lỗi và giám sát khi ứng dụng thực sự xử lý dữ liệu.

## Tài liệu tham khảo

- [Spring Boot 3.5 — Spring Security auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [Spring Security — Hello Spring Security](https://docs.spring.io/spring-security/reference/6.5/servlet/getting-started.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — MockMvc Test Integration](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security — MockMvc WithMockUser/user()](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html)
- [Spring Security — MockMvc CSRF Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Security — Testing HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Boot 3.5.16 release, June 25 2026](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)

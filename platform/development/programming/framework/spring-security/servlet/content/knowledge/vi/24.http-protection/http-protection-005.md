# X-Frame-Options, CSP frame-ancestors và chống clickjacking

> **Phạm vi:** Spring Security trên Servlet stack (Spring Boot 3.x, Spring Security 6.x, Java 17+). Bài học giải thích cách ngăn website không đáng tin nhúng giao diện của ứng dụng vào `iframe`/`frame` để đánh lừa thao tác người dùng, cách đặt các HTTP response header bảo vệ và cách kiểm tra chúng.

## 1. Mục tiêu và tình huống thực tế

Giả sử một ứng dụng tài chính có trang `https://bank.example.test/confirm` với nút **Xác nhận**. Người dùng đã đăng nhập vào ngân hàng trong một tab. Kẻ tấn công tạo trang khác, đặt một `iframe` gần như trong suốt chứa trang xác nhận của ngân hàng, rồi bố trí nút “Nhận thưởng” nằm đè lên vị trí nút thực tế. Khi nạn nhân cố bấm “Nhận thưởng”, thao tác có thể rơi vào nút của trang được nhúng.

Đây là một dạng **clickjacking** (UI redressing): kẻ tấn công thao túng cách giao diện được trình bày để người dùng vô tình tương tác với tài nguyên khác. Kỹ thuật có thể tận dụng bố cục chồng lớp, độ mờ, vị trí con trỏ, cuộn trang hoặc các biến thể đánh lừa hiển thị. Điều kiện khai thác phụ thuộc cách ứng dụng xác thực, cookie, tương tác và trình duyệt; không phải mọi trang nhúng đều tự động bị tấn công.

Điểm then chốt: **same-origin policy (SOP)** thường ngăn JavaScript ở trang của kẻ tấn công đọc DOM của `iframe` ngân hàng, nhưng không nhất thiết ngăn việc **hiển thị trang trong iframe** hoặc việc người dùng trực tiếp nhấp vào nội dung của nó. **CORS** chủ yếu kiểm soát khả năng JavaScript đọc phản hồi cross-origin, không thay thế biện pháp chống nhúng trang.

Sau bài này, bạn sẽ biết cách:

- Xác định ranh giới bảo vệ của `X-Frame-Options` (XFO) và `Content-Security-Policy: frame-ancestors ...`.
- Chọn chính sách **cấm nhúng**, **chỉ cùng origin**, hoặc **cho phép một số origin đối tác**.
- Thiết lập response header trong `SecurityFilterChain` của Spring Security Servlet.
- Hiểu quan hệ giữa XFO, CSP, SOP, CORS, CSRF, cookie và các bộ lọc Spring Security.
- Kiểm tra HTTP header, hành vi iframe thực tế và lỗi triển khai thường gặp.

## 2. Clickjacking xảy ra như thế nào?

Một luồng minh họa:

```text
Người dùng đã xác thực với ứng dụng A
                  |
                  v
Mở trang do kẻ tấn công kiểm soát (B)
                  |
                  v
B cố nhúng trang thao tác nhạy cảm của A trong <iframe>
                  |
                  v
B che phủ / sắp đặt giao diện làm người dùng bấm nhầm
                  |
                  v
Nếu trình duyệt cho nhúng và các điều kiện khác cho phép,
thao tác có thể được gửi tới A bằng ngữ cảnh phiên của người dùng.
```

Khác với việc kẻ tấn công gửi request API trực tiếp, clickjacking thường **mượn chính thao tác hợp lệ của người dùng**. Vì thế chỉ kiểm tra “người dùng đã đăng nhập chưa?” hoặc “người dùng có quyền bấm nút này không?” có thể chưa đủ. CSRF token cũng không phải biện pháp chống clickjacking hoàn chỉnh: một thao tác thực sự được gửi từ giao diện của ứng dụng có thể đi kèm token hợp lệ.

Phòng vệ cơ bản là **không cho origin không được tin cậy nhúng tài liệu nhạy cảm**. Trình duyệt kiểm tra chính sách trong **HTTP response của trang đang bị nhúng**, thường được gọi là *child document* hay *framed document*. Quyền nhúng do chính ứng dụng A công bố, không phải do trang B tự quyết định.

Lưu ý phạm vi: XFO và `frame-ancestors` chặn nội dung bị nhúng trong browsing context như `iframe` hoặc `frame`; chúng không ngăn người dùng truy cập trang trực tiếp ở tab riêng, không sửa lỗ hổng XSS và không thay thế authorization trên server.

## 3. X-Frame-Options: bảo vệ ngắn gọn và tương thích hệ thống cũ

`X-Frame-Options` là HTTP **response header** khai báo liệu tài liệu có được phép hiển thị bên trong frame/iframe hay không.

Các giá trị cần nhớ:

| Giá trị | Ý nghĩa | Khi nào dùng |
|---|---|---|
| `X-Frame-Options: DENY` | Không cho nhúng bởi bất kỳ trang nào, kể cả cùng origin | Trang tài khoản, quản trị, thanh toán, xác nhận thao tác; mặc định tốt khi không có nhu cầu iframe |
| `X-Frame-Options: SAMEORIGIN` | Cho phép nhúng trong phạm vi cùng origin theo cách trình duyệt hỗ trợ | Ứng dụng thực sự cần iframe nội bộ cùng origin |
| `X-Frame-Options: ALLOW-FROM ...` | Giá trị lịch sử, **đã lỗi thời và không được hỗ trợ nhất quán** | Không sử dụng để whitelist đối tác |

Ví dụ response bảo vệ trang:

```http
HTTP/1.1 200 OK
Content-Type: text/html
X-Frame-Options: DENY

<!doctype html>
<html lang="vi"><body>Trang quản lý tài khoản</body></html>
```

Chính sách áp dụng ngay cả khi trang không chứa nội dung bí mật; ví dụ một nút tạo thanh toán hiển thị trên trang có thể là mục tiêu clickjacking. Đừng chỉ gắn header ở API trả JSON rồi bỏ qua chính response HTML nhạy cảm.

**`SAMEORIGIN` dùng khái niệm origin, không chỉ cùng tên miền.** Với `https://app.example.test:443`, một iframe từ `https://app.example.test:8443` hoặc `http://app.example.test` là **khác origin** do port hoặc scheme khác. Không dùng `SAMEORIGIN` nếu cần nhúng từ `https://partner.example.test`: đó vẫn là một origin khác.

**Hạn chế của XFO:** chỉ có hai lựa chọn thực tế là DENY hoặc SAMEORIGIN. XFO không có danh sách nhiều origin đáng tin. Việc kiểm tra các ancestor trong trang nhúng lồng nhau cũng có khác biệt lịch sử giữa trình duyệt. Vì thế ứng dụng hiện đại thường dùng CSP `frame-ancestors` để diễn đạt policy rõ và chi tiết hơn; XFO vẫn có ích làm lớp bảo vệ tương thích với những trình duyệt cũ khi policy tương ứng.

## 4. CSP frame-ancestors: chính sách ai được nhúng tài liệu

`frame-ancestors` là một directive thuộc HTTP header `Content-Security-Policy` (CSP). Nó chỉ ra **origin nào được phép trở thành ancestor** khi nhúng tài liệu. Trình duyệt kiểm tra **mọi ancestor** trong chuỗi frame lồng nhau: một ancestor không phù hợp có thể khiến việc nhúng thất bại dù iframe trực tiếp nằm trên origin được phép.

Những mẫu chính sách:

```http
# Cấm mọi nơi nhúng, kể cả chính ứng dụng
Content-Security-Policy: frame-ancestors 'none'

# Chỉ các trang có cùng origin với tài liệu được nhúng
Content-Security-Policy: frame-ancestors 'self'

# Cho nhúng từ chính origin và một cổng thông tin đối tác cụ thể
Content-Security-Policy: frame-ancestors 'self' https://portal.example.test

# Cho nhúng từ hai origin cụ thể
Content-Security-Policy: frame-ancestors https://portal.example.test https://reports.example.test
```

Những dòng trên là **các lựa chọn riêng biệt**, không phải một response chứa nhiều giá trị mâu thuẫn. Trên thực tế, server gửi header CSP thích hợp cho endpoint tương ứng; các dòng bắt đầu bằng `#` chỉ là chú thích minh họa, không phải cú pháp HTTP header.

Các điểm cần hiểu chính xác:

1. `'none'` từ chối mọi ancestor; `'self'` tương ứng origin của **tài liệu đích**, không phải origin trang mẹ.
2. Các source như `https://portal.example.test` cần được chọn có chủ đích; scheme, host và port ảnh hưởng tới cách đối chiếu. Tránh whitelist rộng như `*` hoặc mọi subdomain nếu không thực sự tin cậy.
3. `frame-ancestors` kiểm soát **ai được nhúng trang này**. Ngược lại, `frame-src` / `child-src` (trên trang mẹ) ảnh hưởng **trang mẹ được tải frame nào**. Hai chiều này độc lập và có thể cùng cần thỏa.
4. `default-src` **không phải fallback** cho `frame-ancestors`. Nếu một CSP chỉ có `default-src 'none'` mà không có `frame-ancestors`, bạn chưa tuyên bố hạn chế ancestor nhúng trang.
5. `frame-ancestors` phải được gửi qua **HTTP response header**. Không dựa vào thẻ `<meta http-equiv="Content-Security-Policy">` để thiết lập directive này: trình duyệt không hỗ trợ nó qua meta.
6. Header `Content-Security-Policy-Report-Only` phục vụ thử nghiệm/báo cáo theo hỗ trợ của trình duyệt; **để thật sự chặn nhúng, triển khai policy thực thi trong `Content-Security-Policy`** và kiểm thử trên browser.
7. CSP có thể chứa nhiều directive, ví dụ `default-src 'self'; script-src 'self'; frame-ancestors 'none'`. Chỉ thêm `frame-ancestors` không đồng nghĩa toàn bộ phần còn lại của CSP đã được bảo vệ khỏi XSS.

CSP `frame-ancestors` cho phép biểu diễn nhu cầu nhúng từ đối tác cụ thể mà XFO SAMEORIGIN không hỗ trợ. Tuy nhiên, đối tác được phép nhúng là một **ranh giới tin cậy**: nếu origin đó bị XSS hoặc bị chiếm quyền, nó có thể trở thành môi trường thực hiện clickjacking. Chỉ allowlist nguồn bạn kiểm soát/đánh giá được.

## 5. Khi cùng gửi X-Frame-Options và frame-ancestors

Trong các trình duyệt hiện đại có hỗ trợ CSP `frame-ancestors` ở chế độ thực thi, policy này có thể **được ưu tiên hơn** XFO cho quyết định nhúng. Trình duyệt cũ lại có thể áp dụng XFO và chưa hiểu `frame-ancestors`. Không nên cố dựa vào một sự kết hợp mâu thuẫn rồi hy vọng các browser chọn giống nhau.

| Yêu cầu | X-Frame-Options | CSP frame-ancestors | Ý nghĩa triển khai |
|---|---|---|---|
| Không trang nào được nhúng | `DENY` | `'none'` | Hai header nhất quán, bảo vệ cả trình duyệt hiện đại và nhiều trình duyệt cũ |
| Chỉ nhúng nội bộ cùng origin | `SAMEORIGIN` | `'self'` | Hai chính sách tương thích về chủ đích |
| Cho phép origin đối tác cụ thể | XFO không diễn đạt được | `'self' https://portal.example.test` hoặc chỉ đối tác | Không cấu hình XFO trái policy; cân nhắc khả năng browser cũ thiếu bảo vệ/hỗ trợ đối tác |
| Không cần iframe | `DENY` | `'none'` | Chọn mặc định đóng, chỉ mở khi có yêu cầu sản phẩm rõ ràng |

Với trường hợp **đối tác khác origin**, cách cấu hình thường thấy là **không phát XFO trên endpoint cho phép nhúng** và sử dụng CSP `frame-ancestors` có allowlist chính xác. Đánh đổi: browser cũ không hỗ trợ directive này có thể thiếu kiểm soát nhúng. Hãy đánh giá đối tượng browser được hỗ trợ; nếu cần chính sách an toàn cho browser cũ, cân nhắc dùng riêng nội dung/đường dẫn nhúng không chứa chức năng nhạy cảm thay vì mở cả trang tài khoản.

Trong Spring Security 6, cấu hình header mặc định thường đã bật **X-Frame-Options: DENY**. Vì vậy chỉ bổ sung CSP cho đối tác có thể chưa đủ: XFO mặc định vẫn ảnh hưởng đến browser cũ, tạo hành vi khác nhau. Khi thay đổi policy, phải kiểm tra **HTTP response thực tế** trên từng endpoint và qua proxy/CDN.

## 6. Ví dụ chạy được: Spring Security Servlet chặn mọi iframe

### 6.1. Dự án và cấu trúc tệp

Ví dụ tối thiểu dùng Spring Boot 3.3.x, Spring Security 6.x, Java 17. Cần Gradle Wrapper của dự án; mẫu khai báo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Tạo hai lớp Java trong package `demo.frame`.

**Tệp `src/main/java/demo/frame/FrameDemoApplication.java`:**

```java
package demo.frame;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class FrameDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FrameDemoApplication.class, args);
    }

    @GetMapping(value = "/protected-ui", produces = MediaType.TEXT_HTML_VALUE)
    public String protectedUi() {
        return """
                <!doctype html>
                <html lang="vi">
                <head>
                  <meta charset="utf-8">
                  <title>Frame protection demo</title>
                </head>
                <body>
                  <h1>Trang được bảo vệ</h1>
                  <button type="button">Nút minh họa</button>
                </body>
                </html>
                """;
    }
}
```

**Tệp `src/main/java/demo/frame/SecurityHeadersConfig.java`:**

```java
package demo.frame;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityHeadersConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/protected-ui").permitAll()
                .anyRequest().denyAll())
            .headers(headers -> headers
                // XFO bảo vệ trên các trình duyệt có hỗ trợ.
                .frameOptions(frame -> frame.deny())
                // CSP nêu rõ: không origin nào được nhúng trang.
                .contentSecurityPolicy(csp ->
                    csp.policyDirectives("frame-ancestors 'none'")));

        // Không thay đổi CSRF, session hay authentication để cấu hình header.
        return http.build();
    }
}
```

**Giải thích code:** `SecurityFilterChain` của Servlet được gọi qua chuỗi filter bảo mật trước khi tạo response. `headers(...)` cài cơ chế gửi security headers. `frameOptions(...deny())` đặt `X-Frame-Options: DENY`; `contentSecurityPolicy(...)` gửi `Content-Security-Policy: frame-ancestors 'none'`. Endpoint `/protected-ui` được `permitAll()` chỉ để ai cũng có thể tải trang và quan sát hiệu lực header. Việc cấm nhúng **không phụ thuộc** vào việc trang có yêu cầu đăng nhập; trang có đăng nhập cũng nên nhận header tương ứng. `anyRequest().denyAll()` chỉ để demo không vô tình mở endpoint khác.

Khi tích hợp vào hệ thống thật, **giữ nguyên các rule xác thực, phân quyền, session và CSRF đang hoạt động**; chỉ thay đổi phần header trong đúng `SecurityFilterChain`. Nếu ứng dụng có nhiều chain hoặc reverse proxy, kiểm tra chain nào thực sự xử lý URL của trang nhạy cảm.

### 6.2. Chạy và xem header

Trong dự án có Gradle Wrapper:

```bash
./gradlew bootRun
```

Ở terminal khác:

```bash
curl -s -D - -o /dev/null http://localhost:8080/protected-ui
```

Trong phần header phản hồi, cần thấy **các dòng tương đương**:

```http
HTTP/1.1 200
X-Frame-Options: DENY
Content-Security-Policy: frame-ancestors 'none'
Content-Type: text/html
```

Đây là các dòng quan trọng được trích ra, **không phải toàn bộ response chính xác**; server có thể phát thêm header và thứ tự khác nhau. `curl` xác minh server có gửi header, nhưng `curl` **không thi hành** chính sách chống iframe như trình duyệt.

### 6.3. Kiểm tra bằng trình duyệt

Tạo tệp `frame-test/index.html` bên ngoài ứng dụng:

```html
<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><title>Iframe test</title></head>
<body>
  <h1>Trang thử nhúng</h1>
  <iframe
    src="http://localhost:8080/protected-ui"
    title="Protected UI"
    width="600"
    height="300"></iframe>
</body>
</html>
```

Có thể phục vụ file ở port 5173 bằng một static server local, ví dụ khi đã cài Python 3:

```bash
cd frame-test
python -m http.server 5173
```

Mở `http://localhost:5173`. Trình duyệt hiện đại sẽ **không hiển thị nội dung `/protected-ui` trong iframe** và thường ghi thông báo ở DevTools Console rằng frame bị từ chối do CSP `frame-ancestors` hoặc XFO. Tab Network vẫn có thể cho thấy response **200** từ server: đó không mâu thuẫn, vì trình duyệt từ chối **render** tài liệu bên trong iframe theo header nhận được.

Để xác minh `DENY` thật sự cấm **cả nhúng cùng origin**, dùng một trang thử được phục vụ từ `http://localhost:8080` trong môi trường test, rồi nhúng `/protected-ui`: kết quả vẫn phải bị chặn. Tránh kết luận từ một lỗi CORS trên `fetch`; iframe navigation và CORS là hai cơ chế khác nhau.

### 6.4. Kiểm thử tự động với MockMvc

Tệp `src/test/java/demo/frame/SecurityHeadersTest.java`:

```java
package demo.frame;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityHeadersTest {
    @Autowired
    MockMvc mvc;

    @Test
    void protectedPageDeclaresAntiFramingHeaders() throws Exception {
        mvc.perform(get("/protected-ui"))
            .andExpect(status().isOk())
            .andExpect(header().string("X-Frame-Options", "DENY"))
            .andExpect(header().string(
                "Content-Security-Policy", "frame-ancestors 'none'"));
    }
}
```

Chạy:

```bash
./gradlew test
```

Test kiểm tra **hợp đồng response headers** của Spring Security Servlet. Nó không phải trình duyệt thật, nên để nghiệm thu chống clickjacking vẫn cần bước nhúng iframe bằng browser ở mục 6.3.

## 7. Chọn policy khác khi có nhu cầu nhúng hợp lệ

Đừng cấm iframe một cách máy móc nếu sản phẩm thực sự có màn hình nhúng. Cần xác định rõ **trang nào được nhúng**, **từ origin nào** và **mức độ tin cậy của origin đó**.

### 7.1. Chỉ được nhúng cùng origin

Thay phần `headers(...)` của ví dụ bằng:

```java
.headers(headers -> headers
    .frameOptions(frame -> frame.sameOrigin())
    .contentSecurityPolicy(csp ->
        csp.policyDirectives("frame-ancestors 'self'")))
```

Đoạn code này **chỉ là thay thế cấu hình trong `HttpSecurity` của dự án ở mục 6**, không phải một file Java độc lập. Khi đó, các trang tại chính origin của `/protected-ui` có thể nhúng nó, còn trang tại origin khác bị từ chối.

Ví dụ `https://app.example.test/reports` và `https://app.example.test/details` là cùng origin, còn `https://dashboard.example.test` không cùng origin, dù cùng tên miền cấp cao.

### 7.2. Cho phép cổng thông tin đối tác khác origin

Giả sử cần nhúng **một trang báo cáo riêng** tại `/embed/report` bên trong `https://portal.example.test`. Với CSP:

```http
Content-Security-Policy: frame-ancestors 'self' https://portal.example.test
```

Cấu hình Spring Security 6 cho **chain riêng chỉ áp dụng trên `/embed/**`** có thể dùng:

```java
.headers(headers -> headers
    // XFO không thể liệt kê origin đối tác khác origin.
    // Chỉ disable trên chain/phạm vi nhúng đã được kiểm soát.
    .frameOptions(frame -> frame.disable())
    .contentSecurityPolicy(csp -> csp.policyDirectives(
        "frame-ancestors 'self' https://portal.example.test")))
```

Đây là **đoạn thay thế cấu hình**, chưa phải ứng dụng hoàn chỉnh. Muốn dùng nó, hãy thiết kế `securityMatcher("/embed/**")` và thứ tự các chain rõ ràng (nếu có nhiều chain); bảo đảm chain của `/account/**`, `/admin/**`, `/payment/**` vẫn áp dụng chính sách chặn nhúng. Không sửa XFO cho toàn bộ hệ thống chỉ để hiển thị một widget.

**Trade-off bắt buộc:** khi tắt XFO trên endpoint nhúng, những browser cũ không hỗ trợ CSP `frame-ancestors` có thể không được bảo vệ. Với nội dung nhạy cảm, có thể cần chọn kiến trúc cung cấp **dữ liệu/widget hạn chế** thay vì cho nhúng nguyên trang có khả năng thay đổi trạng thái.

Kể cả khi đối tác được phép nhúng, API/trang vẫn phải kiểm tra session, authorization và giới hạn hành động. Nếu trang nhúng dùng cookie đăng nhập, browser có thể hạn chế **third-party cookies** hoặc áp dụng `SameSite`; CSP cho nhúng **không bảo đảm** phiên đăng nhập hoạt động.

### 7.3. Frame lồng nhau và nguồn tin cậy

Giả sử `A` nhúng `B`, `B` nhúng trang nhạy cảm `C`. Nếu C chỉ cho phép ancestor B nhưng **không cho phép A**, `frame-ancestors` của C vẫn có thể chặn. Đừng chỉ whitelist origin của iframe ngay bên ngoài; phải xét toàn bộ chuỗi ancestor được thiết kế.

Hạn chế frame bằng CSP cũng có tác động tới tích hợp đối tác, dashboard, báo cáo và các tác vụ tự động chụp giao diện; cần kiểm tra cả nhu cầu hợp lệ. Tuy nhiên không nên cho phép origin rộng chỉ để sửa lỗi nhúng ở một môi trường kiểm thử.

## 8. Điều các header này không thay thế

| Cơ chế | Bảo vệ chính | Khác với anti-framing |
|---|---|---|
| XFO / CSP `frame-ancestors` | Hạn chế bên nào có thể nhúng một tài liệu | Trực tiếp giảm rủi ro clickjacking qua iframe |
| Same-origin policy | Hạn chế truy cập dữ liệu/DOM giữa các origin trong browser | Không luôn ngăn một trang khác nhúng giao diện |
| CORS | Cho phép có điều kiện script đọc response cross-origin | Không ngăn clickjacking bằng iframe |
| Authentication | Xác định danh tính/phiên người dùng | Một người dùng đã đăng nhập vẫn có thể bị dụ nhấp nhầm |
| Authorization | Kiểm tra quyền hành động/tài nguyên | Người có quyền vẫn có thể bị đánh lừa thao tác |
| CSRF protection | Chống một số request giả mạo dựa trên phiên trình duyệt | Một lần nhấp trên giao diện hợp lệ vẫn có thể gửi token đúng |
| Cookie `SameSite` | Giới hạn điều kiện trình duyệt gửi cookie theo quan hệ site | Khác origin chưa chắc khác site; cookie policy không phải biện pháp anti-framing đầy đủ |
| CSP `script-src` / chống XSS | Hạn chế thực thi script và injection | Không thay `frame-ancestors` |
| CSP `frame-src` | Giới hạn frame mà **trang này** được tải | Không quyết định ai được nhúng **trang này** |

Không phụ thuộc vào JavaScript tự phát hiện `window.top !== window.self` rồi chuyển trang (*frame-busting*) để chống clickjacking: script có thể không chạy, bị sandbox hoặc bị can thiệp; HTTP header do trình duyệt thực thi là tuyến phòng vệ chính. Ngoài ra, iframe `sandbox` trên trang mẹ giới hạn một số quyền của tài liệu con nhưng không thay thế việc **trang đích tự kiểm soát ancestor**.

Các giao diện nhạy cảm còn cần xác thực lại khi phù hợp, hiển thị rõ thông tin giao dịch, kiểm tra quyền ở backend, giới hạn rate, chống XSS và áp dụng CSP toàn diện. XFO/`frame-ancestors` là một phần của bảo vệ HTTP.

## 9. Kiểm tra trong môi trường có Spring Security, reverse proxy hoặc CDN

Trong hệ thống nhiều lớp, header có thể được thêm, sửa hoặc mất ở servlet filter, gateway, reverse proxy, CDN. Đừng chỉ đọc file cấu hình rồi mặc định header luôn đúng.

Quy trình kiểm tra thực tế:

1. **Xác định URL trang HTML cần bảo vệ** và tất cả đường dẫn trả giao diện tương đương (trang đăng nhập, màn hình thao tác, endpoint lỗi HTML, ứng dụng quản trị). Với SPA, HTML entry point thường là response chính cần anti-framing.
2. **Đọc response cuối cùng qua domain thật** bằng `curl -D -` hoặc DevTools Network; xác nhận XFO/CSP trên response 200, 302/401/403 theo thiết kế và nội dung HTML nhạy cảm. Header trên response redirect không thay thế header của tài liệu cuối.
3. **Thử iframe từ origin không cho phép** bằng browser thật; xác nhận trang không hiển thị và xem console. Sau đó thử origin được phép (nếu policy không phải `'none'`) để tránh chặn chức năng hợp lệ.
4. **Kiểm tra nhiều `SecurityFilterChain`**. Rule trong một chain không đương nhiên áp dụng cho chain khác. Với nội dung nhúng đối tác, xác minh chain của URL đó thật sự được chọn, và chain mặc định vẫn khóa trang nhạy cảm.
5. **Đối chiếu headers do nhiều tầng phát ra**. Các policy khác nhau có thể dẫn tới hành vi bất ngờ giữa browser. Không để proxy ghi đè CSP chặt thành CSP rộng, xóa XFO hoặc xuất hai giá trị XFO không nhất quán.
6. **Kiểm thử frame lồng nhau và cookie/session** nếu sản phẩm có portal nhiều lớp. Cần phân biệt “CSP chặn frame” với “được nhúng nhưng không có cookie đăng nhập” và lỗi ứng dụng khác.

### Ma trận nghiệm thu

| Trường hợp | XFO/CSP dự kiến | Kết quả browser |
|---|---|---|
| Trang tài khoản không cần iframe | `DENY` + `frame-ancestors 'none'` | Nhúng từ mọi origin đều bị chặn |
| Trang báo cáo chỉ iframe nội bộ | `SAMEORIGIN` + `frame-ancestors 'self'` | Cùng origin được phép; ngoài origin bị chặn |
| Trang widget cho một đối tác | CSP allowlist exact origin trên endpoint riêng | Chỉ origin đối tác/`'self'` nếu có khai báo; mọi ancestor phải phù hợp |
| Người dùng mở tài liệu trực tiếp ở tab mới | Bất kỳ anti-framing header hợp lệ | Trang vẫn mở bình thường; header chỉ ảnh hưởng nhúng |
| Nhúng qua chuỗi A → B → C | CSP frame-ancestors của C có allowlist | Một ancestor bị cấm khiến C không được nhúng |
| Reverse proxy triển khai thêm CSP | Kiểm tra response cuối cùng | Không có policy bị làm rộng/ghi đè/mâu thuẫn ngoài ý muốn |

## 10. Lỗi phổ biến và cách sửa

**1. Chỉ đặt `frame-src 'none'` rồi tưởng đã chống bị nhúng.** `frame-src` nói trang **của mình** được nhúng nội dung từ đâu. Phải dùng `frame-ancestors` trên **trang cần ngăn người khác nhúng**.

**2. Đặt `frame-ancestors` trong thẻ `meta`.** Directive này không được áp dụng khi khai báo qua HTML meta; phải dùng HTTP response header.

**3. Dùng `ALLOW-FROM` để cho phép một đối tác.** Giá trị này lỗi thời; dùng CSP `frame-ancestors` với origin cụ thể và chính sách tương thích browser rõ ràng.

**4. Chỉ thêm CSP cho đối tác mà quên XFO mặc định của Spring Security.** Trong browser hỗ trợ khác nhau, kết quả nhúng có thể khác. Kiểm tra header response thực tế, chọn policy có chủ đích, và chỉ bỏ XFO trên đúng trang cho phép nhúng khi cần.

**5. Cấu hình bảo vệ trên iframe mẹ thay vì HTML con.** Header anti-framing phải nằm trên response của tài liệu **được nhúng**. Trang mẹ cũng có policy riêng để giới hạn nguồn frame nó tải.

**6. Bỏ XFO và mở `frame-ancestors *` cho toàn bộ website để sửa một iframe lỗi.** Vô tình tạo bề mặt clickjacking lớn. Chỉ mở endpoint có nghiệp vụ nhúng và duy trì bảo vệ ở các phần còn lại.

**7. Chỉ dùng `curl`, thấy 200 rồi cho rằng bảo vệ không hoạt động.** HTTP response vẫn có thể thành công; chính trình duyệt quyết định từ chối **render trong iframe**. Phải làm thử nghiệm browser.

**8. Cho rằng XFO/CSP thay CSRF, quyền truy cập hoặc chống XSS.** Đây là cơ chế bổ sung. Giữ authentication, authorization, CSRF và an toàn cookie theo threat model.

## 11. Ghi nhớ

- **Clickjacking** đánh lừa người dùng nhấp vào giao diện được nhúng hoặc che phủ; SOP và CORS không tự chặn kiểu tấn công này.
- **`X-Frame-Options`:** `DENY` để cấm nhúng, `SAMEORIGIN` cho nhúng cùng origin; không dùng `ALLOW-FROM` đã lỗi thời.
- **CSP `frame-ancestors`:** `'none'`, `'self'` hoặc allowlist origin cụ thể; kiểm tra toàn bộ ancestor và chỉ có hiệu lực khi gửi qua response header.
- Khi không cần iframe, **`DENY` + `frame-ancestors 'none'`** là lựa chọn nhất quán. Khi cần đối tác khác origin, dùng CSP allowlist ở endpoint chuyên biệt và hiểu đánh đổi với trình duyệt cũ.
- Trong **Spring Security Servlet**, kiểm soát các header thông qua `SecurityFilterChain.headers(...)`; xác minh ở HTTP response thật và trong iframe bằng browser.
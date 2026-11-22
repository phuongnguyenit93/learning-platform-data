# Đánh giá tác động trước khi nới lỏng chính sách HttpFirewall (Spring Security Servlet)

## 1. Vì sao phải đánh giá tác động?

Trong Spring Security **Servlet**, HttpFirewall là lớp kiểm tra request trước khi Spring Security chọn SecurityFilterChain và áp dụng các quy tắc bảo mật. Triển khai **StrictHttpFirewall** mặc định từ chối nhiều HTTP method hoặc URL có dấu hiệu nguy hiểm hay mơ hồ khi diễn giải: dấu chấm phẩy trong path, dấu gạch chéo đã mã hóa, ký tự backslash, một số chuỗi mã hóa bất thường và những tình huống khác tùy phiên bản.

Khi một client hợp lệ nhận lỗi liên quan đến request bị firewall từ chối, phản xạ “bật allow cho chạy” có thể làm hệ thống hoạt động trở lại nhưng đồng thời mở lại những kiểu request mà thiết kế trước đó cố ngăn chặn. Vì vậy đề bài chính là **đánh giá những gì sẽ thay đổi trước khi nới lỏng chính sách**:

1. Request hợp lệ nào đang bị chặn? Có dữ liệu thực tế chứng minh đó là nhu cầu nghiệp vụ?
2. Tầng nào từ chối request: CDN, reverse proxy, Servlet container, HttpFirewall, authorization hay controller?
3. Chính xác một tùy chọn cho phép thêm **kiểu request** nào, bao gồm cả payload do kẻ tấn công tạo?
4. Proxy, container, Spring MVC và security matcher có hiểu **cùng một đường dẫn và HTTP method** không?
5. Có thể giải quyết bằng thiết kế URL/client hoặc cấu hình đúng ở tầng gốc mà **không cần** thay đổi HttpFirewall không?
6. Nếu buộc phải nới lỏng, kiểm thử nào chứng minh quyền truy cập không bị vượt qua, và cách rollback là gì?

Một phản hồi **4xx**, kể cả 400 hoặc 403, không đủ để kết luận là do HttpFirewall. Phải xác định nguồn lỗi trước khi chọn cách sửa.

## 2. HttpFirewall ở vị trí nào trong luồng request?

Luồng điển hình:

~~~text
Browser / API client
    |
    v
CDN / WAF / Load balancer / Reverse proxy (nếu có)
    |  Có thể decode, rewrite hoặc chuẩn hóa path
    v
Servlet container (Tomcat / Jetty / Undertow)
    |  Parse HTTP request; có thể tự từ chối một số URL
    v
Spring Security FilterChainProxy
    |
    +-- HttpFirewall kiểm tra và bọc HttpServletRequest
    |     |
    |     +-- Từ chối: RequestRejectedException
    |     |       -> cơ chế xử lý lỗi, status phụ thuộc cấu hình
    |     |
    |     +-- Chấp nhận: tiếp tục
    |
    +-- Chọn SecurityFilterChain theo request matcher
    +-- Authentication / Authorization / CSRF / các filter khác
    |
    v
DispatcherServlet -> Spring MVC handler -> service -> database
~~~

**HttpFirewall thực hiện kiểm tra trước khi các matcher của Spring Security quyết định áp dụng chain nào**. Nó giúp giảm nguy cơ request path được các tầng hiểu khác nhau, tạo ra lỗ hổng bỏ qua security matcher. StrictHttpFirewall là lớp lọc mạnh, nhưng không thay thế chuẩn hóa/validation ở proxy, container, framework và business layer.

Nếu container hoặc proxy đã từ chối request, request **có thể chưa từng đến** HttpFirewall. Ngược lại, nếu một tầng phía trước biến đổi URL trước khi giao đến ứng dụng, firewall chỉ nhìn thấy **biểu diễn sau biến đổi**. Đây là lý do kiểm thử chỉ bằng một MockHttpServletRequest không đủ để chứng minh toàn bộ hệ thống an toàn.

**Hai triển khai cần phân biệt:**

- **StrictHttpFirewall**: mặc định nghiêm ngặt, là lựa chọn thích hợp để đánh giá từ baseline bảo thủ.
- **DefaultHttpFirewall**: hành vi khác, có thể xử lý hoặc chuẩn hóa một số đường dẫn theo cách bớt nghiêm ngặt. Không nên đổi nguyên triển khai chỉ để xử lý một trường hợp bị chặn; tác động lớn hơn việc thay đổi một quy tắc cụ thể.

Ngoài kiểm tra path, StrictHttpFirewall còn có các quy tắc về method, host, header/parameter và ký tự không hợp lệ theo phiên bản. Khi xem một lỗi thực tế, phải xác định **kiểm tra nào** gây lỗi, không quy mọi RequestRejectedException về “URL encoded”.

## 3. Phân loại những thay đổi thường được đề xuất

Các tên dưới đây là ví dụ API của **StrictHttpFirewall**; cần đối chiếu phiên bản Spring Security đang chạy và phân tích request thực tế trước khi dùng.

| Đề xuất thay đổi | Tình huống hợp lệ có thể gặp | Rủi ro cần xem trước |
| --- | --- | --- |
| **setAllowSemicolon(true)** | Ứng dụng cũ dùng matrix parameters như /items;color=red | Path parameter và route/security matcher diễn giải khác nhau; che giấu đường dẫn bị bảo vệ |
| **setAllowUrlEncodedSlash(true)** | ID cũ nhúng dấu / dưới dạng %2F trong path variable | Proxy/container decode %2F thành /, thay đổi ranh giới path segment; matcher và controller nhận path khác |
| **setAllowBackSlash(true)** | Client cũ gửi dấu \ trong URL | Một số tầng coi backslash như slash; phát sinh path traversal hoặc bypass matcher |
| **setAllowUrlEncodedPercent(true)** | Đầu vào chứa ký hiệu % đã mã hóa thành %25 | Double decoding: %252F có thể được giải mã nhiều lần thành /; sai lệch cách xác định path |
| Nới giới hạn ký tự hoặc dạng mã hóa đường dẫn khác | Legacy client xuất URL không chuẩn | Chuẩn hóa, Unicode, dấu phân cách, ký tự điều khiển hoặc traversal không nhất quán |
| **setAllowedHttpMethods(...)** theo danh sách mới | Một client cần phương thức HTTP bổ sung | Mở rộng attack surface; method lạ bị proxy/container hoặc routing layer xử lý khác |
| Dùng HttpFirewall ít nghiêm ngặt hoặc tùy biến hàng loạt | Muốn “cho chạy mọi URL” | Khó xác định chính xác những hàng rào nào đã bị vô hiệu |

**Lưu ý quan trọng:** một URL chứa chuỗi **%2F**, **;**, **\\** hoặc **%25** có thể bị proxy/Servlet container xử lý khác nhau trước khi tới ứng dụng. Bảng trên mô tả **nhóm rủi ro cần kiểm chứng**, không tuyên bố mọi stack sẽ có cùng response cho từng chuỗi.

Một thay đổi có thể giải quyết đúng request hợp lệ mà vẫn để lộ bypass ở request khác. Quy trình kiểm thử phải bao gồm cả **trường hợp tốt** lẫn **trường hợp đối kháng gần giống**.

## 4. Hiểu gốc rủi ro: khác biệt giữa các cách diễn giải URL

### 4.1. Path của proxy, Servlet và security matcher phải thống nhất

Giả sử endpoint cần bảo vệ:

~~~text
/admin/reports/**  -> ADMIN
/public/**         -> permitAll
~~~

Với request bình thường **/admin/reports/2026**, đường dẫn rõ ràng. Nhưng các biến thể như:

~~~text
/admin;tracking=x/reports/2026
/admin%2Freports/2026
/admin//reports/2026
/admin/%2e%2e/public/x
/admin%5Creports/2026
~~~

có thể bị những tầng khác nhau hiểu khác nhau, hoặc bị từ chối ngay ở proxy/container. **Không suy đoán** rằng từng payload ở trên có thể bypass trên ứng dụng cụ thể; mục đích là kiểm tra sự thống nhất: sau mọi bước decode/normalization, **authorization phải áp dụng cho đúng tài nguyên thực sự được phục vụ**.

Nếu một matcher quyết định “không phải /admin/**” nhưng bộ định tuyến cuối cùng phục vụ tài nguyên quản trị, chính sách đang có lỗ hổng nghiêm trọng. Một ca test quan trọng là yêu cầu không xác thực **không bao giờ** lấy được dữ liệu quản trị dù URL được biểu diễn theo biến thể được chấp nhận.

### 4.2. Semicolon và matrix variables

Spring MVC có thể hỗ trợ matrix variables với cú pháp dạng:

~~~text
/products;color=red;size=m
~~~

Nếu client cũ thật sự cần dấu **;**, phương án **setAllowSemicolon(true)** có thể được cân nhắc. Tuy nhiên, cần kiểm tra:

- Security matcher dùng request path nào; cách nhận diện path parameters có tương thích Spring MVC router không?
- Proxy/container có giữ nguyên hoặc xóa phần sau dấu chấm phẩy không?
- URL mang semicolon có thể xuất hiện ở đường dẫn admin hoặc đường dẫn mà kiểm soát quyền dựa vào path không?
- Hệ thống cache/CDN có phân biệt **/a** và **/a;x=1** giống backend hay không?
- Có cần matrix variables thật, hay client có thể chuyển sang query parameters, ví dụ **/products?color=red**?

**Cho phép ; không đồng nghĩa có thể bỏ qua kiểm thử authorization của mọi route**. Một thay đổi global ảnh hưởng toàn bộ ứng dụng, kể cả những endpoint không dùng matrix variables.

### 4.3. Encoded slash, backslash, double encoding

Một ID logic như **region/east** nếu đặt vào một path segment có thể bị client mã hóa thành **region%2Feast**. Nếu proxy giải mã thành **region/east**, số segment sẽ khác. Điều này ảnh hưởng cả route matching, access control và cache key.

Ví dụ double encoding:

~~~text
%2F   -> /
%252F -> %2F -> /   (nếu hai tầng giải mã kế tiếp nhau)
~~~

Đây là **chuỗi minh họa khả năng double-decoding**, không phải hành vi tất yếu của Servlet container. Cần quan sát rõ **mỗi tầng giải mã bao nhiêu lần**. Với Windows-oriented components, **\\** đôi khi được xử lý như dấu phân cách, nhưng web stack không nhất thiết giống nhau.

Trước khi cho phép encoded slash, xem xét thiết kế lại API: dùng **query parameter**, **request body**, hoặc **opaque ID** chỉ gồm ký tự URL-safe như base64url. Tránh phụ thuộc vào việc encoded path separator được giữ nguyên qua mọi proxy.

### 4.4. HTTP method và header

Nới danh sách HTTP methods có thể mở thêm cách truy cập các endpoint mà quy tắc phân quyền hoặc proxy không kiểm tra tương đương. Ví dụ TRACE thường bị chặn trong cấu hình nghiêm ngặt. Cần khảo sát cả **method override** do filter/proxy thực hiện: backend có thể thấy method đã chuyển đổi thay vì method gốc.

Đừng nhầm firewall với CORS: **allowedMethods của CORS** chỉ kiểm soát browser cross-origin, còn danh sách **allowed HTTP methods** của StrictHttpFirewall kiểm tra request thực tế tới ứng dụng. CORS không ngăn curl gửi method bị ứng dụng chấp nhận.

## 5. Phải có bằng chứng về false positive trước khi thay đổi

Một ticket “request bị chặn” cần tối thiểu:

| Dữ liệu cần thu thập | Mục đích |
| --- | --- |
| Chức năng bị lỗi, tên client và phiên bản | Xác nhận đây là luồng nghiệp vụ được hỗ trợ |
| Endpoint và method kỳ vọng | Xác định phạm vi quyền và dữ liệu |
| Dạng URL/path an toàn đã che thông tin nhạy cảm | Tìm ký tự/encoding gây lỗi mà không phát tán secret |
| Status, loại exception, thông điệp từ proxy/container/app | Xác định tầng thực sự từ chối |
| Tần suất, tỷ lệ ảnh hưởng, môi trường | Định lượng mức độ ảnh hưởng của thay đổi |
| Các biến đổi path ở CDN/proxy/container | Biết request firewall thực sự nhìn thấy |
| SecurityFilterChain và authorization matcher dự kiến | Kiểm tra path được bảo vệ đúng |
| Những client hợp lệ và client không tin cậy có thể tiếp cận | Đánh giá attack surface |

**Không log nguyên URL khi nó có token, email, secret hoặc dữ liệu cá nhân.** Với chẩn đoán, dùng fingerprint hoặc mẫu ký tự đã làm sạch, request ID, route/category và exception type; đặt retention/permission phù hợp. Không ghi cookie, Authorization header, CSRF token, session ID hoặc request body vào log chỉ vì cần theo dõi RequestRejectedException.

### Phân biệt lỗi theo vị trí

1. **Không có access log tại ứng dụng:** kiểm tra WAF, proxy và container trước; kết luận “StrictHttpFirewall chặn” có thể sai.
2. **Có RequestRejectedException trước controller:** xem chính sách HttpFirewall nào từ chối; trace qua request ID, exception class, thông tin sanitized.
3. **Có 401/403 sau khi vào security chain:** kiểm tra authentication, authorization, CSRF. Nới HttpFirewall có thể không giải quyết.
4. **Có 404 hoặc handler không match:** request có thể đã qua firewall nhưng MVC router không hiểu path. Nới firewall chưa chắc giúp.
5. **Browser hiển thị CORS error:** cần kiểm tra CORS/preflight độc lập; không thay HttpFirewall khi chưa chứng minh liên quan.

Cần đối chiếu điều kiện **request path** ở cả proxy và ứng dụng. Dù chỉ sửa một setter, request hợp lệ có thể chưa chạy được nếu tầng trước đã reject.

## 6. Mẫu đánh giá rủi ro trước khi cho phép ngoại lệ

Một quyết định tốt mô tả **trước/sau**, phạm vi thay đổi và biện pháp kiểm soát. Có thể dùng biểu mẫu sau trong ticket thiết kế (đây là mẫu đánh giá, không phải thông số cấu hình):

| Tiêu chí | Câu hỏi bắt buộc |
| --- | --- |
| Nhu cầu | Request nào đang thất bại và vì sao không sửa client? |
| Thay đổi chính xác | Setter, giá trị cũ/mới, môi trường, phiên bản Spring Security? |
| Phạm vi | Tất cả route hay chỉ một nhóm? Những hệ thống nào chịu ảnh hưởng? |
| Threat model | Đối tượng tấn công có thể tạo URL/method/header ra sao? |
| Path interpretation | CDN, proxy, container, Spring Security và Spring MVC có cùng cách hiểu không? |
| Authorization | Các URL khác biệt nhưng dẫn đến cùng tài nguyên được phân quyền giống nhau không? |
| Tests | Negative, positive, regression, integration, fuzz input nào phải pass? |
| Quan sát | Metric lỗi/latency/403/404, dấu hiệu bypass, ngưỡng rollback? |
| Owner và phê duyệt | Ai chịu trách nhiệm bảo mật, API, vận hành, thời điểm triển khai? |
| Rollback | Có thể hoàn tác bằng config/deploy nào, dữ liệu có bị ảnh hưởng? |

**Ví dụ quyết định:** một client cũ chỉ dùng **/products;color=blue**, và nhóm sản phẩm chứng minh không thể cập nhật client ngay. Nếu chọn nới **setAllowSemicolon(true)**, phải kiểm thử cả route công khai và quản trị, cache/proxy behavior, mọi matcher hiện có, rồi triển khai có giám sát. Nếu có thể chuyển client sang **/products?color=blue**, đây thường là cách giảm bề mặt tấn công hơn.

Không sử dụng điểm rủi ro số học tự đặt làm bằng chứng an toàn. Quyết định phải dựa trên tình huống nghiệp vụ, mapping quyền, cấu hình thực và kết quả test.

## 7. Chiến lược thay đổi ít nhất có thể

Ưu tiên giải pháp theo nguyên nhân:

1. **Client tạo URL sai:** sửa URL encoding và API contract; ngăn client tự nối path từ dữ liệu không tin cậy.
2. **Thiết kế path mơ hồ:** chuyển dữ liệu có dấu slash/semicolon sang query, body hoặc ID URL-safe.
3. **Proxy decode/rewrite không nhất quán:** sửa cách proxy forward path, kiểm tra thêm container.
4. **Chức năng thật sự cần cú pháp hiếm:** chứng minh không thể thay contract ngay, chọn **đúng một** ngoại lệ của StrictHttpFirewall, thử nghiệm độc lập và đo tác động.
5. **Client gửi method đặc biệt:** xác định rõ use case và route, thay đổi danh sách method có kiểm chứng; tuyệt đối không mở method chỉ để ngừng báo lỗi.

Với **StrictHttpFirewall**, nhiều setter áp dụng cho firewall xử lý request ở phạm vi ứng dụng/filter chain; đừng mặc định rằng chỉ một controller hoặc path được “nới”. Nếu yêu cầu thật sự chỉ áp dụng tại một khu vực, cần thiết kế ranh giới riêng và kiểm thử chi tiết; bản thân việc gọi một setter global không tạo giới hạn theo endpoint.

**Không chọn một cấu hình “accept all”** chỉ vì test happy path thành công. Các request đột biến, khai thác mơ hồ đường dẫn và method lạ thường nằm ngoài happy path.

## 8. Ví dụ Java 17: giữ baseline nghiêm ngặt và đánh giá ngoại lệ trong test

Đây là ví dụ **Spring Security Servlet** với **Spring Boot 3.4.5 / Java 17**. Ứng dụng thực tế sử dụng StrictHttpFirewall mặc định. Bài kiểm thử riêng sẽ chứng minh điều gì xảy ra nếu **chỉ** cho phép dấu chấm phẩy trong một đối tượng firewall **cô lập**, chưa thay đổi chính sách production.

Cấu trúc:

~~~text
firewall-review/
├── pom.xml
└── src/
    ├── main/java/example/firewall/FirewallReviewApplication.java
    └── test/java/example/firewall/FirewallPolicyTest.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>firewall-review</artifactId>
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

**src/main/java/example/firewall/FirewallReviewApplication.java**:

~~~java
package example.firewall;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.firewall.StrictHttpFirewall;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class FirewallReviewApplication {
    public static void main(String[] args) {
        SpringApplication.run(FirewallReviewApplication.class, args);
    }
}

@Configuration
class FirewallSecurityConfiguration {
    @Bean
    WebSecurityCustomizer firewallCustomizer() {
        return web -> {
            StrictHttpFirewall firewall = new StrictHttpFirewall();
            // Giữ nguyên chính sách mặc định. Không nới toàn hệ thống.
            web.httpFirewall(firewall);
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/admin/**").hasRole("ADMIN")
                        .anyRequest().permitAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class FirewallDemoController {
    @GetMapping("/public/ping")
    Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @GetMapping("/admin/report")
    Map<String, String> report() {
        return Map.of("report", "private");
    }
}
~~~

**Ý nghĩa:** đường dẫn **/public/ping** cho phép truy cập công khai, **/admin/report** yêu cầu role ADMIN. Dù không có bước nới firewall, các security matcher vẫn phải bảo vệ đúng route. Nếu sau này sửa quy tắc path, phải kiểm thử lại rằng các biến thể URL không thể khiến route quản trị trở thành công khai.

### Test trực tiếp sự khác biệt trước/sau của một setter

**src/test/java/example/firewall/FirewallPolicyTest.java**:

~~~java
package example.firewall;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.web.firewall.FirewalledRequest;
import org.springframework.security.web.firewall.RequestRejectedException;
import org.springframework.security.web.firewall.StrictHttpFirewall;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.mock.web.MockHttpServletRequest;

@SpringBootTest
@AutoConfigureMockMvc
class FirewallPolicyTest {
    @Autowired
    MockMvc mvc;

    private static MockHttpServletRequest request(String method, String path) {
        MockHttpServletRequest req = new MockHttpServletRequest(method, path);
        req.setServletPath(path);
        return req;
    }

    @Test
    void defaultFirewallRejectsSemicolon() {
        StrictHttpFirewall strict = new StrictHttpFirewall();
        assertThrows(RequestRejectedException.class,
                () -> strict.getFirewalledRequest(
                        request("GET", "/public/items;color=red")));
    }

    @Test
    void isolatedCandidateCanAllowSemicolon() {
        StrictHttpFirewall candidate = new StrictHttpFirewall();
        candidate.setAllowSemicolon(true);
        assertDoesNotThrow(() -> {
            FirewalledRequest wrapped = candidate.getFirewalledRequest(
                    request("GET", "/public/items;color=red"));
            wrapped.reset();
        });
    }

    @Test
    void semicolonExceptionStillRejectsEncodedSlash() {
        StrictHttpFirewall candidate = new StrictHttpFirewall();
        candidate.setAllowSemicolon(true);
        assertThrows(RequestRejectedException.class,
                () -> candidate.getFirewalledRequest(
                        request("GET", "/admin%2Freport")));
    }

    @Test
    void traceMethodIsRejectedByDefault() {
        StrictHttpFirewall strict = new StrictHttpFirewall();
        assertThrows(RequestRejectedException.class,
                () -> strict.getFirewalledRequest(
                        request("TRACE", "/public/ping")));
    }

    @Test
    void adminRouteRequiresAuthentication() throws Exception {
        mvc.perform(get("/admin/report"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void adminRoleCanAccessProtectedRoute() throws Exception {
        mvc.perform(get("/admin/report")
                        .with(user("reviewer").roles("ADMIN")))
                .andExpect(status().isOk());
    }
}
~~~

Chạy:

~~~bash
mvn test
mvn spring-boot:run
~~~

Kết quả kiểm thử mong đợi: **6 bài kiểm thử đều PASS** trong môi trường có Java 17 và Maven, nếu dependencies được tải đầy đủ. Đây là hành vi kỳ vọng của ví dụ; **kết quả runtime cần được chạy xác nhận trong môi trường thật**, không được suy từ văn bản. Sau khi khởi động, có thể gọi **GET /public/ping** và nhận JSON mang **status=ok**. **GET /admin/report** khi chưa đăng nhập phải bị chặn theo security rules.

**Vì sao test candidate không đủ?** Các unit tests trên dùng MockHttpServletRequest với đường dẫn do test kiểm soát. Servlet container/proxy ở production có thể parse hoặc chuẩn hóa URL trước khi request đến firewall. Cho phép request qua **một đối tượng StrictHttpFirewall** chưa chứng minh rằng endpoint tương ứng sẽ route đúng hoặc vẫn được phân quyền đúng. Vì vậy cần thêm integration tests với server và proxy thật.

### Nếu phải đề xuất ngoại lệ vào cấu hình

Sau khi có quyết định được review và kiểm thử integration, thay đổi chính xác có thể chỉ là:

~~~java
StrictHttpFirewall firewall = new StrictHttpFirewall();
firewall.setAllowSemicolon(true); // Chỉ sau đánh giá rủi ro và xác nhận tests
~~~

Đây là **đoạn minh họa thay đổi có điều kiện**, **không phải file cấu hình production hoàn chỉnh** và không được bật trong ứng dụng mẫu. Đặt ngoại lệ đúng nơi WebSecurity đang nhận firewall. Đừng viết đồng thời nhiều setAllow... chỉ để “chữa” hàng loạt request bị reject mà chưa phân tích từng loại.

## 9. Bộ test phải có trước khi nới chính sách

### 9.1. Positive tests: chứng minh nhu cầu thật

- Request bị chặn trước đó phải vượt qua đúng tầng cần thiết khi cấu hình mới được bật.
- Routing phải đến **đúng controller và đúng đối tượng**, không chỉ trả status 2xx giả.
- Authentication, authorization, CSRF và validation vẫn được áp dụng.
- URL, method và request headers thông thường không thay đổi hành vi.
- Frontend, API gateway, WAF, Servlet container và Spring Security dùng cùng chính sách đường dẫn.

### 9.2. Negative tests: chứng minh không mất ranh giới quyền

| Nhóm test | Kỳ vọng bắt buộc |
| --- | --- |
| Truy cập URL quản trị bằng user ẩn danh | Vẫn bị từ chối, bất kể biến thể path |
| User thường gọi endpoint yêu cầu ADMIN | Vẫn bị từ chối |
| Path có ;, %2F, %5C hoặc %25 ở vùng nhạy cảm | Không bypass matcher; nếu được chấp nhận thì route/permission vẫn đúng |
| Path segment trùng/đệm hoặc dot-segment | Không chuyển từ route bảo vệ sang route công khai sau normalization |
| HTTP method ngoài hợp đồng API | Không vô tình thực thi thao tác thay đổi trạng thái |
| Double decode hoặc URL được proxy rewrite | Quyết định phân quyền nhất quán trước và sau route resolution |
| Request header/host bất thường | Không mở thêm ngoài phạm vi đề xuất |
| Các bước login/logout và POST được bảo vệ CSRF | Vẫn yêu cầu token và quyền theo thiết kế |
| Cache/CDN với URL biến thể | Không trộn phản hồi riêng tư/công khai giữa các cache key khác nhau |

Mỗi trường hợp nên có **baseline trước thay đổi**, **kết quả sau thay đổi**, và log/trace cho thấy request được route đi đâu. Những payload liên quan đến quyền phải được thử với cả **anonymous**, **user thường** và **user có quyền**. Không chỉ kiểm tra HTTP status; cần xác nhận **dữ liệu và side effect**.

### 9.3. Tích hợp thực tế

Kiểm thử theo đúng tuyến mạng production hoặc một staging giống production:

~~~text
Client -> WAF/CDN -> Reverse proxy -> Servlet container
       -> HttpFirewall -> SecurityFilterChain -> Controller
~~~

So sánh path theo từng tầng dưới dạng đã che dữ liệu nhạy cảm. Các thông số cần ghi rõ: URL decode/normalization, servlet context path, forwarding headers, phiên bản container, Spring Security và route matching strategy. Hãy thử các dạng URL độc lập, tránh giả định một test MockMvc bảo đảm hành vi của nginx/Tomcat/Envoy hoặc CDN.

**Một sự khác biệt đáng chú ý:** request bị container từ chối trước khi vào Spring có thể không hiện RequestRejectedException. Trường hợp đó phải được giải thích qua access/error log của tầng tương ứng, không đánh dấu false positive của HttpFirewall.

## 10. Quan sát an toàn và rollout

Một đợt nới lỏng có chủ đích nên tách ba mốc:

**Trước triển khai:** ghi baseline request rejected theo nhóm lý do và route, lượng client bị ảnh hưởng, tỷ lệ 4xx/5xx, route quyền cao, các case test đã pass. Dùng log/metric **đã làm sạch**, không lưu raw payload nhạy cảm.

**Trong canary/staging:** so tỷ lệ request hợp lệ thành công với trước đó; quan sát các request bất thường được chấp nhận sau thay đổi, truy cập nhầm controller, cache mismatch, authz deny, CSRF failures và tăng đột biến 5xx. Có cảnh báo cho truy cập bất thường tới endpoint quản trị và thay đổi phân bố URL/method.

**Sau rollout:** tiếp tục giám sát theo thời gian đủ bao phủ traffic thật; lưu ticket quyết định, owner, cấu hình cụ thể và kết quả regression. Nếu xuất hiện bypass security matcher, dữ liệu riêng tư lộ qua cache/route, hoặc request lạ bắt đầu đi sâu đến controller, **rollback ngay** theo kế hoạch, sau đó điều tra.

Rollback không chỉ là trả một boolean về false; nếu deployment/config thay đổi nhiều nơi (gateway, container, application), cần hoàn tác đúng thứ tự và kiểm tra request trở lại baseline. Có thể dùng feature rollout hoặc deployment revision khi phù hợp, nhưng đừng để policy security mặc định phụ thuộc vào thao tác thủ công không theo dõi.

## 11. Sai lầm phổ biến

1. **Từ một lỗi 400 kết luận phải tắt StrictHttpFirewall.** Status chưa chứng minh tầng lỗi.
2. **Bật nhiều setAllow... cùng lúc.** Không biết cái nào thật sự giải quyết nhu cầu, khó đánh giá blast radius và rollback.
3. **Chỉ thử URL hợp lệ.** Không biết các URL biến thể có bypass matcher hay không.
4. **Chỉ kiểm thử Spring MockMvc.** Bỏ qua decode/rewrite tại proxy, gateway và Servlet container.
5. **Tin rằng permitAll() hoặc @CrossOrigin là kiểm soát thay thế.** CORS và authorization không cùng mục đích; permission cần được áp dụng đúng route.
6. **Dùng DefaultHttpFirewall chỉ để “hết lỗi”.** Đổi implementation có thể thay đổi nhiều quy tắc cùng lúc.
7. **Log toàn bộ URL và headers nhằm tìm lỗi.** Có thể làm lộ token/session dữ liệu; chỉ log trường cần thiết đã che.
8. **Nới firewall nhưng bỏ qua path normalization trong cache.** CDN/edge và backend có thể coi hai biến thể URL khác nhau hoặc giống nhau không nhất quán.
9. **Không test lại các route quyền cao sau thay đổi.** Đặc biệt nguy hiểm khi matcher dựa vào request path.
10. **Không có kế hoạch rollback.** Khi phát hiện bypass, độ trễ hoàn tác làm tăng hậu quả.

## 12. Checklist quyết định và kết luận

Trước khi review một pull request thay đổi StrictHttpFirewall, xác nhận tất cả ý sau:

- [ ] Có request hợp lệ tái hiện lỗi với môi trường và phiên bản cụ thể.
- [ ] Đã xác định tầng thực sự từ chối request, không đoán qua status.
- [ ] Đã ghi nhận raw/normalized URL một cách an toàn, so sánh cách xử lý ở các tầng.
- [ ] Đã xác định đúng setter/hành vi cần nới, không đổi hàng loạt.
- [ ] Đã xem xét sửa client, API contract và proxy trước.
- [ ] Đã cập nhật threat model về path confusion, encoding, method và các route nhạy cảm.
- [ ] Unit tests và integration tests có cả happy path lẫn negative authorization cases.
- [ ] Đã kiểm tra phân quyền/CSRF, dữ liệu trả về và side effect dưới URL biến thể.
- [ ] Đã kiểm tra proxy/container/CDN và cache key.
- [ ] Có quan sát, owner, phê duyệt, ngưỡng rollback và cách hoàn tác.

**Nguyên tắc cần nhớ:** nới lỏng HttpFirewall là một **thay đổi bề mặt tấn công**, không chỉ là sửa lỗi đầu vào. Chỉ chấp nhận khi xác định được nhu cầu nghiệp vụ, phạm vi ngoại lệ, cách mọi tầng diễn giải request, và bằng chứng regression cho thấy authentication/authorization/CSRF vẫn được áp dụng đúng tài nguyên. Giữ StrictHttpFirewall nghiêm ngặt làm baseline và chỉ mở ngoại lệ hẹp sau đánh giá có thể kiểm chứng.

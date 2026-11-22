# Kiểm tra dấu gạch chéo cuối, đường dẫn mã hóa và sự thống nhất với MVC trong Spring Security Servlet

## Mục tiêu bài học

Trong một ứng dụng Spring Security Servlet, quyền truy cập thường được cấu hình theo đường dẫn HTTP, ví dụ GET /api/records/{id}. Spring MVC cũng có hệ thống ánh xạ URL vào controller. Hai tầng này phải hiểu **cùng một request theo cách tương thích**: nếu Spring Security nghĩ request thuộc một đường dẫn công khai nhưng Spring MVC lại hiểu đó là đường dẫn bảo vệ, hệ thống có thể vô tình cấp quyền sai. Ngược lại, nếu Security chặn một URL mà MVC chỉ coi là tài nguyên không tồn tại, lập trình viên dễ nhầm lỗi 403 thành lỗi quyền thay vì lệch matcher.

Ba nhóm tình huống đặc biệt đáng kiểm tra là:

1. **Dấu gạch chéo cuối:** /api/records/A123 khác /api/records/A123/ hay không?
2. **Đường dẫn mã hóa (URL encoding):** %2F, %5C, %2E, %25 và mã hóa nhiều lớp sẽ được container, firewall, matcher hoặc MVC xử lý thế nào?
3. **Tính nhất quán:** Spring Security RequestMatcher, Spring MVC HandlerMapping, servlet mapping và reverse proxy có đang áp dụng cùng quy tắc hay không?

Sau bài này, bạn sẽ biết:

- Phân biệt request URI nguyên dạng, đường dẫn đã xử lý bởi Servlet container, servlet path, context path và URI template variable.
- Giải thích vì sao **trailing slash matching mặc định đã thay đổi trong Spring Framework 6** và không nên sao chép hành vi cũ.
- Dùng MvcRequestMatcher với HandlerMappingIntrospector để giảm khác biệt giữa security matching và MVC matching.
- Biết vai trò của StrictHttpFirewall và vì sao request có ký tự mã hóa nguy hiểm có thể bị từ chối **trước** controller.
- Viết ví dụ Java 17+, Spring Boot 3.x / Spring Security 6.x có SecurityFilterChain và controller cùng mẫu đường dẫn.
- Chạy MockMvc test kiểm tra URL chuẩn, URL thừa dấu /, path không khớp, phương thức khác và quyền người dùng.
- Thiết kế kiểm thử HTTP thật khi cần kiểm tra hành vi container/proxy đối với phần trăm mã hóa.
- Không dùng việc nới lỏng firewall hoặc permitAll rộng làm cách “sửa” lỗi URL.

Phạm vi: **Servlet stack** (Spring MVC, Spring Security HTTP), không phải WebFlux. Ví dụ dùng Spring Boot 3.3.x và Spring Security 6.x tương thích theo dependency management. Các hành vi về percent encoding có thể phụ thuộc Servlet container, phiên bản và proxy; những chỗ không có hợp đồng cố định được giải thích theo **bất biến bảo mật** thay vì khẳng định một mã HTTP duy nhất.

## 1. Một URL có nhiều cách nhìn ở các tầng khác nhau

Xét request do client gửi:

~~~text
GET /shop/api/records/A%2F123?view=full HTTP/1.1
Host: example.test
~~~

Nếu ứng dụng triển khai dưới context path /shop, các tầng có thể thấy:

| Thành phần | Thông tin liên quan | Điều cần lưu ý |
| --- | --- | --- |
| Client / reverse proxy | Request target có %2F và query | Proxy có thể từ chối, chuẩn hóa hoặc chuyển tiếp theo cấu hình |
| Servlet container | Request URI, context path, servlet mapping | Container có thể áp dụng chính sách encoded slash trước khi gọi filter |
| Spring Security HttpFirewall | Request đã được firewalled/chuẩn hóa cho matcher | Có thể từ chối URL không an toàn, không nhất thiết để controller nhìn thấy |
| RequestMatcher | Có khớp /api/records/{id} không? | Có thể sử dụng servlet path, path info, MVC matching semantics |
| Spring MVC HandlerMapping | Có controller nhận request không? | Quy tắc path pattern và decoding ảnh hưởng route |
| Controller @PathVariable | Giá trị id được bind như thế nào? | Không mặc định giống từng byte của raw request target |
| Authorization/service | Caller có quyền với record thật không? | Không được suy quyền chỉ bằng raw URL string |

Vì vậy, **không lấy request.getRequestURI() rồi tự split("/") để xây quyền truy cập**, nhất là khi URL có context path, matrix parameter, percent encoding hoặc dấu slash lặp.

Một số khái niệm hữu ích:

- **Request URI** thường bao gồm phần path mà Servlet API trình bày, có thể còn dạng escape tùy method/container; khác query string.
- **Context path** là tiền tố triển khai ứng dụng, ví dụ /shop.
- **Servlet path** và path info phản ánh servlet mapping, không phải tất cả đều là URL công khai nguyên dạng.
- **URI template variable** là giá trị được matcher hoặc HandlerMapping trích từ mẫu như /api/records/{id}.
- **RequestMatcher** quyết định rule bảo mật match hay không.
- **Controller mapping** quyết định controller nào thực thi sau các filter bảo mật.

Không thể suy rằng việc một controller có @GetMapping("/api/records/{id}") sẽ tự tạo rule quyền tương đương trong SecurityFilterChain. Hai cấu hình cần được thiết kế và test cùng nhau.

## 2. Dấu slash cuối: /items/42 và /items/42/

Một khác biệt rất nhỏ ở cuối URL có thể thay đổi đường đi xử lý:

~~~text
GET /api/records/A123      -> /api/records/{id}
GET /api/records/A123/     -> dấu / thừa ở cuối
GET /api/records/A123//    -> hai dấu / cuối
~~~

Trong nhiều ứng dụng Spring MVC cũ, một số cấu hình có thể cho phép optional trailing separator, khiến pattern /users/{id} match cả /users/123/. **Từ Spring Framework 6, mặc định path matching không còn tự coi hai dạng có/không có slash cuối là tương đương.** Nên với Spring Boot 3.x dùng cấu hình MVC phổ biến, /api/records/A123 thường khớp @GetMapping("/api/records/{id}"), còn /api/records/A123/ **không** khớp controller đó.

Điều này khác với việc một cấu hình matcher dùng wildcard hoặc matcher khác có thể match cả hai. Nếu security rule và MVC rule hiểu khác nhau, hai request tương tự bề ngoài có thể có authorization path khác nhau.

### Ví dụ chính sách

Giả sử chỉ người có role READER được đọc record:

~~~java
.requestMatchers(profileMatcher).hasRole("READER")
.anyRequest().denyAll()
~~~

profileMatcher là matcher cụ thể cho GET /api/records/{id}.

- GET /api/records/A123 bởi READER: matcher chuyên biệt match; đi tiếp MVC và trả record nếu hợp lệ.
- GET /api/records/A123/ bởi READER: nếu MVC-style matcher **không match** ở môi trường Boot 3/Spring Framework 6 mặc định, request rơi vào denyAll; kết quả thường **403** cho người đã xác thực.
- GET /api/records/A123/ trong hệ thống có anyRequest().authenticated(): request có thể vượt authorization nhưng MVC không có controller tương ứng, kết quả thường **404**.
- GET /api/records/A123/ với user chưa xác thực: cùng một denyAll có thể dẫn tới entry point/challenge (ví dụ HTTP Basic 401), không nhất thiết 403.

**Điều quan trọng:** 403 không chứng minh MVC đã tìm thấy controller; 404 không chứng minh SecurityFilterChain đã match URL như mong muốn. Muốn tìm đúng nguyên nhân phải xác định từng lớp.

### Có nên chấp nhận cả hai dạng?

Có ba chính sách hợp lệ, cần chọn một cách nhất quán:

1. **Chỉ một URL canonical:** /api/records/A123 hợp lệ; /api/records/A123/ bị từ chối/404. Đây là lựa chọn đơn giản cho API khi contract quy định rõ URL.
2. **Định nghĩa rõ cả hai mapping:** chỉ khi nghiệp vụ thật sự muốn cả hai dạng, cấu hình MVC và Security cho **đúng cả hai**, có test quyền tương đương.
3. **Chuyển hướng về dạng canonical:** với GET/HEAD, thiết kế redirect có kiểm soát và đảm bảo cả request ban đầu lẫn đích được xử lý an toàn; không tự giả định redirect của POST/PUT/DELETE giữ method, body và CSRF giống nhau.

Không bật chính sách chấp nhận slash cuối trên toàn hệ thống chỉ để một controller test pass, vì có thể làm thay đổi route authorization của nhiều endpoint khác. Nếu đang nâng cấp từ Spring Framework 5 lên 6, hãy xem trailing slash như một thay đổi hành vi cần test.

## 3. Encoded path: %2F không đơn giản là dấu / thông thường

URL percent-encoding biểu diễn byte bằng %HH. Một số ví dụ:

| Dạng | Ý nghĩa thường gặp | Vấn đề cần kiểm tra |
| --- | --- | --- |
| %2F hoặc %2f | Dấu / | Có bị container/firewall từ chối? Có thành một segment mới? |
| %5C hoặc %5c | Dấu backslash | Có bị xử lý như separator trên một tầng nào không? |
| %2E | Dấu chấm | Có tham gia dot-segment normalization không? |
| %2E%2E | Hai dấu chấm | Có làm biến đổi đường đi qua normalization không? |
| %25 | Dấu % | Có nguy cơ double decoding thành escape mới không? |
| %20 | Dấu cách | Matcher và validation hiểu input ra sao? |
| %3B | Dấu chấm phẩy | Matrix/path parameters có ảnh hưởng path matching không? |
| %3F | Dấu ? | Có bị xử lý như ký tự path hay thành query separator không? |
| %252F | Một lớp encoding cho chuỗi %2F | Nếu có giải mã thêm lần nữa, có thể xuất hiện dấu / |

**Không có quy tắc an toàn kiểu “decode tất cả URL thật sớm rồi so sánh chuỗi”.** Container, reverse proxy, Spring Security firewall và Spring MVC có thể áp dụng các chính sách khác nhau cho URL đáng ngờ. Có những request bị từ chối ở tầng hạ tầng trước khi đi tới AuthorizationManager; có những request được nhận nhưng phải bị loại bởi validation hoặc authorization ở tầng ứng dụng.

Ví dụ:

~~~text
/api/records/part%2Fother
/api/records/part%252Fother
/api/records/part%5Cother
/api/records/%2E%2E/admin
/api/records/A%20B
/api/records/A;v=1
/api//records/A123
~~~

Các request này là **đầu vào để kiểm thử**, không phải danh sách URL được bảo đảm hoạt động hay nhận đúng một status. Tomcat, proxy và StrictHttpFirewall có thể xử lý trước khi MVC nhận request.

### Tại sao encoded slash nhạy cảm?

Dấu / phân tách các segment đường dẫn. Nếu tầng Security đánh giá một request là một segment chứa chuỗi %2F, nhưng tầng MVC hoặc một proxy lại giải mã thành hai segment rồi ánh xạ route khác, ta có thể tạo sai lệch trong quyết định quyền.

Ví dụ conceptual:

~~~text
Client gửi: /public/abc%2Fprivate
Tầng A hiểu: /public/{name}       (một segment)
Tầng B hiểu: /public/abc/private  (nhiều segment)
~~~

Đây là **mô hình rủi ro**, không khẳng định cấu hình Spring Boot mẫu bên dưới thực sự bị bypass. Spring Security và Servlet container cung cấp biện pháp phòng vệ, đặc biệt bằng firewall mặc định. Không tắt các biện pháp chỉ vì URL “trông bình thường” dưới cách nhìn của browser.

### Double encoding đáng quan tâm ở đâu?

Giả sử client gửi %252F. Sau một lần giải mã, có thể thu được %2F; sau lần giải mã thứ hai, thành /. Nếu các tầng giải mã khác số lần, logic quyền truy cập và logic route có thể bất đồng.

Quy tắc thực tiễn:

- Không tự decode lần thứ hai trên giá trị đã do MVC bind thành @PathVariable.
- Không tạo URL nội bộ cho downstream bằng cách nối chuỗi path chưa validate.
- Nếu business identifier có ký tự phân tách, xem xét truyền dưới dạng query/body, dùng opaque ID an toàn trong URL hoặc hợp đồng encoding được chuẩn hóa toàn hệ thống.
- Test cả mã hóa một lớp và hai lớp trên **cổng HTTP thực** sau proxy, không chỉ dùng MockMvc.

## 4. StrictHttpFirewall là hàng rào cho request nguy hiểm

Spring Security Servlet đi qua FilterChainProxy, trong đó HttpFirewall có vai trò kiểm tra các dạng URL có thể gây bất đồng giữa container và matcher. Một implementation mặc định thường được dùng là **StrictHttpFirewall**, có chính sách bảo thủ với nhiều ký tự hoặc biểu diễn đường dẫn nguy hiểm.

Trong cấu hình thông dụng, StrictHttpFirewall **từ chối** các dạng có khả năng gây sai lệch như URL-encoded slash, backslash, dấu chấm phẩy/path parameter hoặc một số kiểu mã hóa phần trăm đáng ngờ. Tập điều kiện chính xác và cách phản hồi có thể thay đổi theo phiên bản/framework config.

Cần phân biệt:

1. **Firewall từ chối request:** authorization manager và controller có thể chưa chạy. Response có thể do RequestRejectedHandler hoặc container quyết định, không có một status bất biến cho mọi hạ tầng.
2. **Matcher không khớp rule:** request đã qua firewall nhưng rơi vào một rule khác, ví dụ anyRequest().denyAll().
3. **MVC không có route:** authorization đã cho đi tiếp nhưng DispatcherServlet không chọn được controller; thường 404.
4. **Controller/service từ chối identifier:** request match route nhưng ID không hợp lệ theo miền nghiệp vụ; có thể 400 hoặc 404.

Đừng chữa một RequestRejectedException bằng cách lập tức:

~~~java
// KHÔNG SAO CHÉP VÀO CẤU HÌNH MẪU:
// firewall.setAllowUrlEncodedSlash(true);
// firewall.setAllowBackSlash(true);
// firewall.setAllowSemicolon(true);
~~~

Các dòng trên là minh họa **một loại thay đổi chính sách có rủi ro**, không phải khuyến nghị. Nới firewall có thể mở lại các URL mà container, proxy hoặc MVC diễn giải khác nhau. Nếu có yêu cầu đặc biệt phải hỗ trợ ký tự đó, cần kiểm thử từng tầng, xác định route contract và security implications trước khi cấp phép hẹp.

Không dùng WebSecurityCustomizer.ignoring() để bỏ qua Spring Security filter chain cho URL không hiểu rõ. Ngoài authorization, việc bỏ qua chain có thể mất kiểm soát firewall/security headers và các bộ lọc khác của ứng dụng.

### Status code khi bị firewall từ chối

Một RequestRejectedException có thể được xử lý thành HTTP 400 trong nhiều thiết lập Spring Security mới, nhưng cách xử lý cụ thể tùy Spring Security version, RequestRejectedHandler và container/proxy. **Không đóng đinh** “%2F luôn là 400” hoặc “%2F luôn là 403” trong tài liệu kiểm thử dùng cho mọi môi trường.

Bất biến quan trọng cho tài nguyên được bảo vệ: **một URL bất thường không được vượt qua kiểm tra authentication/authorization hoặc đi vào một controller nhạy cảm không dự kiến.**

## 5. Đồng bộ URL matching giữa Security và Spring MVC

Cả Spring Security và Spring MVC đều làm việc với request path, nhưng không dùng API hoàn toàn giống nhau.

- **Spring MVC HandlerMapping** quyết định controller bằng @GetMapping, @RequestMapping, PathPatternParser và cấu hình MVC.
- **Spring Security RequestMatcher** quyết định rule trong authorizeHttpRequests. Có các implementation khác nhau với ngữ nghĩa path riêng.
- **MvcRequestMatcher** dùng HandlerMappingIntrospector để bám theo cơ chế matching của MVC ở nơi phù hợp.
- **StrictHttpFirewall** kiểm soát request trước khi các matcher/security filters xử lý; nó không thay MVC route.
- **Servlet container và proxy** có thể từ chối hoặc biến đổi request trước khi Spring nhận được.

Để giảm lệch, với một ứng dụng Spring MVC dùng Spring Security 6, có thể dùng **MvcRequestMatcher.Builder** với HandlerMappingIntrospector và cùng pattern/method với controller:

~~~java
MvcRequestMatcher.Builder mvc =
        new MvcRequestMatcher.Builder(introspector);

MvcRequestMatcher readRecord =
        mvc.pattern(HttpMethod.GET, "/api/records/{id}");
~~~

Sau đó dùng cùng mẫu trong MVC:

~~~java
@GetMapping("/api/records/{id}")
public ResponseEntity<String> read(@PathVariable String id) {
    // Xử lý bản ghi, kiểm tra dữ liệu và quyền nghiệp vụ.
}
~~~

Hai snippet này chưa đủ để tạo một chương trình độc lập; code Spring Boot đầy đủ có ở phần 7.

**MvcRequestMatcher không phải lời hứa rằng mọi dạng URL bất thường đều được tự động đồng nhất.** Nó không quản lý được cách reverse proxy và container xử lý raw path trước đó, cũng không tự biến mọi path variable thành ID an toàn. Với nhiều DispatcherServlet hoặc servlet mapping không chuẩn, cần cấu hình servletPath phù hợp và test SecurityFilterChain thực tế.

### Vì sao nên khai báo HTTP method?

GET /api/records/A123 và DELETE /api/records/A123 có thể cần quyền khác nhau. Matcher chỉ pattern mà không giới hạn method có thể áp dụng một policy đọc quá rộng cho method thay đổi dữ liệu.

Ví dụ:

~~~java
mvc.pattern(HttpMethod.GET, "/api/records/{id}");
~~~

cho phép bạn áp role READER cho GET. Với POST/PUT/PATCH/DELETE, tạo policy riêng khi nghiệp vụ có endpoint tương ứng. Nếu dùng một URL pattern chung cho mọi method, hãy bảo đảm kiểm tra quyền của các hành động nhạy cảm.

### Thứ tự authorization rule rất quan trọng

Đoạn cấu hình sau có nguy cơ:

~~~java
.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").permitAll()
        .requestMatchers(readRecord).hasRole("READER")
        .anyRequest().denyAll())
~~~

Nếu /api/** match trước, rule READER phía sau có thể không được xét. Không suy rằng một rule sau cùng có quyền cao hơn sẽ tự chặn rule trước. **Đặt matcher hẹp trước và không mở wildcard quá rộng để che các biến thể URL.**

## 6. Ứng dụng mẫu và chính sách mong đợi

Chúng ta viết một API Spring MVC nhỏ:

- GET /public/ping được phép truy cập khi chưa đăng nhập.
- GET /api/records/{id} cần role READER.
- Các URL/method khác bị từ chối bằng anyRequest().denyAll().
- ID record hợp lệ trong demo chỉ gồm chữ ASCII, số, dấu gạch dưới và dấu gạch ngang, dài từ 1 đến 40 ký tự.
- Với user READER, GET /api/records/A123 trả 200; GET /api/records/A123/ không khớp rule MVC-style theo mặc định của Boot 3.3/Spring Framework 6 và thường rơi vào denyAll.
- User VIEWER bị từ chối dù URL chuẩn.
- Anonymous nhận Basic authentication challenge khi vào tài nguyên cần quyền.
- Encoded-path input được kiểm thử riêng vì status có thể phụ thuộc hạ tầng.

Một sơ đồ:

~~~text
HTTP request
    |
Servlet container (phân tích request target)
    |
Spring Security StrictHttpFirewall
    |
FilterChainProxy chọn SecurityFilterChain
    |
HTTP Basic authentication (nếu header có credentials)
    |
MvcRequestMatcher(GET, "/api/records/{id}")
    |
    +-- khớp -> hasRole("READER")
    |              |
    |              +-- có quyền -> DispatcherServlet -> MVC @GetMapping
    |              +-- thiếu quyền -> 403 (authenticated)
    |
    +-- không khớp -> anyRequest().denyAll()
                                  |
                                  +-- từ chối hoặc challenge
~~~

Chính sách **denyAll ngoài route đã biết** là quyết định học tập để dễ thấy khác biệt: nếu SecurityFilterChain không match URL, request không được đi tới controller hoặc tài nguyên khác. Một hệ thống có thêm route khác sẽ cần thêm rule cụ thể, chứ không được copy cấu hình mẫu rồi ngạc nhiên khi endpoint khác bị chặn.

## 7. Ví dụ Java 17 + Spring Boot 3.3.x + Spring Security 6.x

### 7.1. Cấu trúc project

~~~text
mvc-path-matching-lab/
  settings.gradle
  build.gradle
  gradlew / gradlew.bat (khi đã tạo Gradle Wrapper)
  src/main/java/dev/example/pathmatching/
    PathMatchingApplication.java
    SecurityConfig.java
    RecordController.java
  src/test/java/dev/example/pathmatching/
    PathMatchingIntegrationTest.java
~~~

settings.gradle:

~~~groovy
rootProject.name = 'mvc-path-matching-lab'
~~~

build.gradle:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Mỗi tệp Java cần đặt đúng package và path. Lệnh ./gradlew cần Gradle Wrapper thực sự tồn tại, có thể lấy từ Spring Initializr hoặc chạy gradle wrapper trong một môi trường Gradle tương thích trước khi dùng.

### 7.2. Entry point

Tệp src/main/java/dev/example/pathmatching/PathMatchingApplication.java:

~~~java
package dev.example.pathmatching;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathMatchingApplication {

    public static void main(String[] args) {
        SpringApplication.run(PathMatchingApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfig sử dụng MvcRequestMatcher

Tệp src/main/java/dev/example/pathmatching/SecurityConfig.java:

~~~java
package dev.example.pathmatching;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.MvcRequestMatcher;
import org.springframework.web.servlet.handler.HandlerMappingIntrospector;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                        .password(encoder.encode("local-reader-pass"))
                        .roles("READER").build(),
                User.withUsername("viewer")
                        .password(encoder.encode("local-viewer-pass"))
                        .roles("VIEWER").build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            HandlerMappingIntrospector introspector) throws Exception {

        MvcRequestMatcher.Builder mvc =
                new MvcRequestMatcher.Builder(introspector);

        MvcRequestMatcher publicGet =
                mvc.pattern(HttpMethod.GET, "/public/ping");

        MvcRequestMatcher recordGet =
                mvc.pattern(HttpMethod.GET, "/api/records/{id}");

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(publicGet).permitAll()
                        .requestMatchers(recordGet).hasRole("READER")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
~~~

Các điểm cần chú ý:

1. Dùng MvcRequestMatcher.Builder(introspector) để security matcher theo ngữ nghĩa path của Spring MVC.
2. Khai báo GET rõ ràng. POST/PUT/DELETE cùng path không mặc nhiên có quyền READER.
3. Rule công khai chỉ dành cho GET /public/ping. Không có permitAll("/api/**").
4. Record rule dùng hasRole("READER"); User.withUsername(...).roles("READER") tạo authority ROLE_READER.
5. anyRequest().denyAll() bảo vệ các path chưa được liệt kê, bao gồm nhiều biến thể URL không hợp lệ.
6. httpBasic cho phép dùng curl/MockMvc với account demo; không lưu credential thật trong code.
7. Không tự nới StrictHttpFirewall. Không chỉnh trailing slash matching để “ép” test pass.
8. Không thêm Servlet securityMatcher chỉ giới hạn một prefix mà chưa hiểu fallback chain: SecurityFilterChain trong ví dụ bao phủ request mặc định.

Trong Spring Boot 3.x có Spring MVC, HandlerMappingIntrospector được cung cấp từ MVC configuration. Với ứng dụng có nhiều servlet mapping, có thể cần cấu hình MvcRequestMatcher.Builder.servletPath(...) theo nơi DispatcherServlet xử lý request; **context path và servlet path là hai khái niệm khác nhau**.

### 7.4. Controller có ID validation

Tệp src/main/java/dev/example/pathmatching/RecordController.java:

~~~java
package dev.example.pathmatching;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RecordController {

    @GetMapping("/public/ping")
    public String ping() {
        return "PUBLIC_OK";
    }

    @GetMapping("/api/records/{id}")
    public ResponseEntity<String> record(
            @PathVariable("id") String id) {

        if (!id.matches("[A-Za-z0-9_-]{1,40}")) {
            return ResponseEntity.badRequest().body("INVALID_ID");
        }

        return ResponseEntity.ok("RECORD:" + id);
    }
}
~~~

Vì sao kiểm tra ID thêm một lần trong controller?

- Authorization rule đảm bảo người gọi có ROLE_READER; nó **không tự xác minh định dạng business ID**.
- Chỉ cho phép ký tự alphanumeric ASCII, dấu _ và dấu - giúp mẫu demo không vô tình diễn giải dấu /, %, dấu chấm hoặc ký tự điều khiển thành ID hợp lệ.
- Đây chỉ là **input validation**, không phải ownership authorization. Nếu record gắn với một user/tenant thật, service phải tra bản ghi và kiểm tra caller có quyền trên record đó.
- Nếu request chứa encoded slash bị từ chối bởi container/firewall trước controller, đoạn regex có thể không được gọi; không xem regex là giải pháp thay thế firewall.

Một ứng dụng thật có thể dùng UUID cho record ID, hoặc chuyển định danh phức tạp sang body/query với validation nhất quán. Không cố hỗ trợ mọi ký tự tùy ý trong một path segment chỉ để giữ nguyên một chuỗi người dùng nhập.

### 7.5. MockMvc kiểm thử những trường hợp có kết quả ổn định

Tệp src/test/java/dev/example/pathmatching/PathMatchingIntegrationTest.java:

~~~java
package dev.example.pathmatching;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PathMatchingIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsAccessibleWithoutCredentials() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("PUBLIC_OK"));
    }

    @Test
    void readerCanUseCanonicalRoute() throws Exception {
        mvc.perform(get("/api/records/A123")
                        .with(httpBasic("reader", "local-reader-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("RECORD:A123"));
    }

    @Test
    void viewerCannotReadCanonicalRoute() throws Exception {
        mvc.perform(get("/api/records/A123")
                        .with(httpBasic("viewer", "local-viewer-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void unauthenticatedCanonicalRouteChallengesForBasicAuth()
            throws Exception {
        mvc.perform(get("/api/records/A123"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void trailingSlashDoesNotMatchMvcPatternInDefaultConfig()
            throws Exception {
        mvc.perform(get("/api/records/A123/")
                        .with(httpBasic("reader", "local-reader-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void extraSegmentDoesNotBypassSecurityRule() throws Exception {
        mvc.perform(get("/api/records/A123/extra")
                        .with(httpBasic("reader", "local-reader-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void queryParameterDoesNotChangeThePathVariable() throws Exception {
        mvc.perform(get("/api/records/A123")
                        .queryParam("id", "B999")
                        .with(httpBasic("reader", "local-reader-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("RECORD:A123"));
    }

    @Test
    void differentHttpMethodIsNotAllowedByGetRule() throws Exception {
        mvc.perform(post("/api/records/A123")
                        .with(httpBasic("reader", "local-reader-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void malformedBusinessIdentifierIsRejectedIfRouteMatches()
            throws Exception {
        mvc.perform(get("/api/records/A.123")
                        .with(httpBasic("reader", "local-reader-pass")))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("INVALID_ID"));
    }
}
~~~

Chạy test:

~~~bash
./gradlew test
~~~

Lệnh này yêu cầu Gradle Wrapper có trong project. Với Windows PowerShell, có thể dùng .\gradlew.bat test.

**Vì sao trailing slash test kỳ vọng 403 thay vì 404?** Với default MVC-style matcher của cấu hình mẫu, GET /api/records/A123/ không match recordGet. Rule còn lại là anyRequest().denyAll(), nên người dùng đã được HTTP Basic xác thực bị từ chối trong Spring Security trước khi request đến MVC. Nếu thay cấu hình thành anyRequest().authenticated(), một request từ reader có thể vượt tầng HTTP authorization và bị MVC trả 404 vì không có controller. Đó là **hai policy khác nhau**, không phải một bug 403/404 của framework.

**Vì sao POST test có thể cần điều chỉnh khi security chain bổ sung CSRF?** Trong cấu hình mẫu, POST là unsafe method và CsrfFilter mặc định có thể từ chối trước AuthorizationFilter; dù vậy kết quả vẫn là 403. Test chỉ chứng minh request không được phép, không khẳng định nó đi tới nhánh denyAll. Để chẩn đoán riêng method matcher, có thể gửi CSRF hợp lệ trong test rồi xác minh vẫn bị authorization từ chối.

**Lưu ý về encoded URL:** MockMvc không phải Servlet container hoàn chỉnh nằm sau reverse proxy. Không dùng một MockMvc status để kết luận Tomcat, Nginx hoặc cloud ingress chắc chắn sẽ xử lý %2F/%252F giống hệt.

### 7.6. Chạy ứng dụng và thử các URL

Sau khi project được build:

~~~bash
./gradlew bootRun
~~~

Trong terminal khác, gửi vài request local:

~~~bash
curl -i http://localhost:8080/public/ping

curl -i -u reader:local-reader-pass \
  http://localhost:8080/api/records/A123

curl -i -u reader:local-reader-pass \
  http://localhost:8080/api/records/A123/

curl -i -u viewer:local-viewer-pass \
  http://localhost:8080/api/records/A123
~~~

Trên Windows, câu lệnh nhiều dòng dùng dấu backslash như trên dành cho Bash; có thể nhập mỗi lệnh curl trên một dòng trong terminal phù hợp. Với PowerShell, đôi khi cần dùng curl.exe để tránh alias cho Invoke-WebRequest.

Kỳ vọng theo cấu hình mẫu:

| Request | Kết quả điển hình |
| --- | --- |
| GET /public/ping không có credential | 200, PUBLIC_OK |
| GET /api/records/A123 bằng reader | 200, RECORD:A123 |
| GET /api/records/A123/ bằng reader | 403 theo denyAll |
| GET /api/records/A123 bằng viewer | 403 |
| GET /api/records/A123 không có credential | 401 và Basic challenge |
| GET /api/records/A.123 bằng reader | 400, INVALID_ID |
| GET /api/records/A123/extra bằng reader | 403 theo denyAll |

Bảng mô tả các case ổn định trong project demo với mặc định Boot 3.3.x. Response header và body lỗi có thể khác tùy version/web container. Không gửi password thật trong terminal history hoặc tài liệu. HTTP Basic chỉ dùng cùng HTTPS ở môi trường có dữ liệu thật; base64 của Authorization header **không phải mã hóa bảo mật**.

## 8. Test encoded path bằng HTTP stack thật, không đoán status

Để kiểm tra encoded slash/double encoding, khởi động ứng dụng bằng bootRun, sau đó chạy các request trên **cổng HTTP thực**. Nếu dùng curl, thêm --path-as-is để tránh một số biến đổi URL phía client đối với dấu chấm/slash; tuy nhiên curl option không kiểm soát được cách server/proxy xử lý.

~~~bash
curl --path-as-is -i -u reader:local-reader-pass \
  'http://localhost:8080/api/records/A%2FB'

curl --path-as-is -i -u reader:local-reader-pass \
  'http://localhost:8080/api/records/A%252FB'

curl --path-as-is -i -u reader:local-reader-pass \
  'http://localhost:8080/api/records/A%5CB'

curl --path-as-is -i -u reader:local-reader-pass \
  'http://localhost:8080/api/records/A;v=1'

curl --path-as-is -i -u reader:local-reader-pass \
  'http://localhost:8080/api//records/A123'
~~~

**Không chép một status giả định vào checklist.** Ghi kết quả thực tế của mỗi request tại hạ tầng đang test: URL đã gửi, status, Location header nếu có, endpoint/controller nào thực sự chạy, và rule security nào được chọn. Có thể gặp 400, 403 hoặc 404 tùy tầng từ chối. Nếu một biến thể được phép vào controller, ID validation của ví dụ cũng loại nhiều ký tự không hợp lệ.

Bất biến cần giữ: request lạ không được tự động bỏ qua quyền hoặc truy cập một endpoint nhạy cảm khác do giải mã khác tầng. Một số mã hóa có thể hợp lệ với URL khác, nhưng chỉ khi sản phẩm chủ động cho phép và đã kiểm thử matcher, dữ liệu ID và policy.

### Test trong môi trường có reverse proxy

Nếu production có Ingress/Nginx/Apache/API gateway:

1. Thử trực tiếp vào backend Servlet trong môi trường kiểm soát để biết hành vi của container và Spring Security.
2. Thử qua đúng public domain/proxy để biết request nào bị rewrite, 301/308 hoặc reject.
3. Ghi lại raw request target phía client khi có thể, URL được forward vào backend và handler cuối cùng.
4. Thử trailing slash, doubled slash, encoded slash, encoded percent, dot segment, matrix parameter và Unicode theo nhu cầu.
5. Không log credential, session cookie, access token hoặc Authorization header trong quá trình khảo sát.
6. Kiểm tra không có proxy rule bỏ qua authentication trên một path nhưng forward sang một protected path khác.

Quan trọng: nếu proxy redirect /api/records/A123/ về /api/records/A123, request **đích** vẫn phải qua SecurityFilterChain như bình thường. Đừng xem việc canonical redirect là thay thế cho authorization.

## 9. Canonical URL: redirect hay từ chối?

Một API nên có **quy tắc URL canonical** rõ ràng.

Ví dụ:

~~~text
Canonical: /api/records/A123
Không canonical: /api/records/A123/
~~~

Nếu yêu cầu sản phẩm là chấp nhận cả hai dưới dạng một tài nguyên, một phương án là redirect URL có trailing slash về URL canonical. Nhưng cần suy nghĩ về:

- **GET/HEAD:** redirect thường phù hợp, nhưng cache, relative URL và query string phải được xử lý đúng.
- **POST/PUT/PATCH/DELETE:** status 301/302 có lịch sử client đổi method/body; 307/308 giữ method theo ngữ nghĩa HTTP hiện đại nhưng vẫn cần test CSRF, idempotency và authorization.
- **Session/Cookies:** redirect giữa host/scheme có thể đổi cookie scope/SameSite và làm mất phiên hoặc lộ thông tin nếu hạ từ HTTPS xuống HTTP.
- **Open redirect:** không xây Location trực tiếp từ giá trị URL chưa kiểm soát.
- **Authorization trước/sau redirect:** không cho phép một route công khai biến thành alias để bypass route cần auth.
- **Proxy/CDN caches:** cache key và redirect cần nhất quán với chính sách dữ liệu riêng tư.
- **Client/API contracts:** thay đổi canonical URL là thay đổi hành vi có thể tác động SDK/mobile app.

Với API bảo mật, một chính sách **từ chối URL không canonical** cùng mô tả rõ contract thường đơn giản hơn việc tạo redirect phức tạp. Nếu dùng redirect, test end-to-end để chứng minh route cuối vẫn yêu cầu quyền như trước.

## 10. Thống nhất trailing slash và matcher trong ứng dụng nhiều route

Một app lớn thường có route công khai và riêng tư gần nhau:

~~~text
GET /public/info             công khai
GET /api/records/{id}        chỉ READER
POST /api/records            chỉ EDITOR
GET /api/records/{id}/audit  chỉ AUDITOR
~~~

Một rule dạng /api/**.authenticated() chỉ xác minh có login, không kiểm tra đủ READER/EDITOR/AUDITOR. Với những route khác nhau về quyền, nên khai báo rule hẹp và method cụ thể:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(mvc.pattern(HttpMethod.GET,
            "/public/info")).permitAll()
    .requestMatchers(mvc.pattern(HttpMethod.GET,
            "/api/records/{id}/audit")).hasRole("AUDITOR")
    .requestMatchers(mvc.pattern(HttpMethod.GET,
            "/api/records/{id}")).hasRole("READER")
    .requestMatchers(mvc.pattern(HttpMethod.POST,
            "/api/records")).hasRole("EDITOR")
    .anyRequest().denyAll());
~~~

Đây là snippet chính sách cho một app lớn hơn, **không** phải đoạn thêm vào project demo vốn chỉ có READER. Bất kỳ route mới nào cũng cần test URL chuẩn, slash cuối, method khác, role khác và ID validation. Đặt các matcher chuyên biệt trước nếu có khả năng overlap.

Nếu app sử dụng nhiều SecurityFilterChain với @Order và securityMatcher, cần kiểm tra chain đầu tiên match request. Một rule trong chain /api/** không ảnh hưởng một request đi vào chain web khác hoặc không vào chain nào. **Sự nhất quán MVC ↔ Security phải được đảm bảo ở cả cấp chọn chain lẫn cấp authorization matcher.**

## 11. Context path, DispatcherServlet mapping và servletPath

Hai loại tiền tố dễ nhầm:

- **Context path**, ví dụ server.servlet.context-path=/shop, là đường dẫn gốc triển khai web app.
- **Servlet mapping**, ví dụ DispatcherServlet được map ở /app/*, tạo servletPath khác với context path và pathInfo.

Nếu app triển khai tại /shop, URL công khai có thể là /shop/api/records/A123, nhưng MVC @GetMapping vẫn thường khai báo /api/records/{id} tương đối với mapping/context. Không thêm /shop vào mọi requestMatchers chỉ vì browser nhìn thấy /shop.

Với DispatcherServlet không dùng mapping mặc định, MvcRequestMatcher.Builder có phương thức servletPath(...) để chỉ rõ servlet path khi cần:

~~~java
MvcRequestMatcher.Builder mvc =
    new MvcRequestMatcher.Builder(introspector)
        .servletPath("/app");
~~~

Đây là cấu hình **theo điều kiện**, chỉ dùng khi DispatcherServlet của bạn thật sự được map phù hợp với servletPath /app. Không thêm vào project demo mặc định. Trong app có nhiều Servlet, security matcher dựa trên MVC không nên được dùng mù cho URL do servlet khác xử lý.

Cần kiểm tra:

1. Context path thực tế của app;
2. Servlet mapping và servletPath/pathInfo;
3. URL được proxy forward, scheme/host/path;
4. HandlerMappingIntrospector thuộc ApplicationContext phù hợp;
5. FilterChainProxy chọn chain nào;
6. RequestMatcher match hay không;
7. Controller nào được MVC chọn.

## 12. Chẩn đoán khác biệt 400, 401, 403 và 404

| Status | Một nguyên nhân thường gặp | Không nên suy diễn |
| --- | --- | --- |
| 400 | Container/firewall/input validation từ chối path | Không nhất thiết do AuthorizationManager |
| 401 | Chưa xác thực, HTTP Basic entry point challenge | Không có nghĩa route đã tới controller |
| 403 | Đã xác thực nhưng thiếu quyền, denyAll hoặc CSRF/firewall tùy xử lý | Không chứng minh MVC có route |
| 404 | Request đến MVC nhưng không có handler/resource | Không chứng minh URL đã vượt qua mọi security rule có chủ đích |
| 301/302/307/308 | Redirect/canonicalization/security entry point | Phải kiểm tra Location và method ở request tiếp theo |

Vì status không mô tả đủ đường đi, hãy dùng log có giới hạn trong môi trường development:

~~~properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping=TRACE
~~~

Không bật TRACE toàn bộ Spring Security lâu dài trên production hoặc log URL chứa token/credential. Log class/method cụ thể có thể thay đổi giữa phiên bản; không phụ thuộc câu chữ cố định.

Để xác định lỗi:

1. Kiểm tra HTTP method, raw URL và query có đúng không.
2. Xác định request có vào Servlet container hay bị proxy từ chối.
3. Tìm dấu hiệu StrictHttpFirewall/RequestRejectedException.
4. Xác định SecurityFilterChain được chọn, Authentication của caller và RequestMatcher match.
5. Kiểm tra authorization decision, role/authority mapping và anyRequest fallback.
6. Nếu request qua Security, kiểm tra HandlerMapping có chọn đúng controller không.
7. Nếu controller chạy, kiểm tra @PathVariable đã được bind/validate thế nào.
8. Cuối cùng kiểm tra quyền trên bản ghi thật ở service/repository.

Không debug bằng cách disable toàn bộ security hoặc rộng permitAll("/**") trên môi trường có dữ liệu nhạy cảm.

## 13. Bảo mật ở mức dữ liệu vẫn là bắt buộc

Một request match GET /api/records/{id} và caller có ROLE_READER **chưa** chứng minh người đó được đọc **mọi bản ghi**.

Nếu ứng dụng multi-tenant, cần so sánh tenant/owner của record được nạp với danh tính caller đã xác minh. Ví dụ pseudocode ở service:

~~~java
public RecordDto readRecord(String id, AuthenticatedUser caller) {
    Record record = repository.findById(id)
            .orElseThrow(NotFoundException::new);

    if (!record.getTenantId().equals(caller.getTenantId())) {
        throw new AccessDeniedException("Access denied");
    }
    return mapper.toDto(record);
}
~~~

Các class Record, AuthenticatedUser, repository, NotFoundException, mapper ở snippet này **chỉ minh họa nghiệp vụ**, không phải chương trình Java độc lập. Điều cần giữ là **ID trong URL do client chọn không tự xác lập ownership**. Dùng principal/tenant ID đáng tin, truy vấn có điều kiện và transaction phù hợp khi dữ liệu quan trọng.

Các kỹ thuật URL matching ở bài này bảo vệ điểm vào HTTP. Khi service có thể được gọi qua message consumer, batch job hoặc method nội bộ, cân nhắc method/service-level authorization độc lập với RequestMatcher HTTP để phòng IDOR/BOLA.

## 14. Checklist kiểm thử regression khi nâng cấp framework

Đặc biệt khi nâng Spring Framework 5 lên 6 hoặc thay MVC/path matching:

1. **Liệt kê endpoint quan trọng** và canonical URL của từng endpoint.
2. **Xác minh trailing slash:** /route và /route/ có cùng kết quả theo contract hay không?
3. **Giới hạn HTTP method:** GET, POST, PUT, PATCH, DELETE có rule riêng phù hợp.
4. **Kiểm thử anonymous/roles:** quyền owner, admin, user khác; không chỉ test đúng credentials.
5. **Kiểm thử encoded slash/backslash/percent/dot:** request bị reject hoặc được xử lý an toàn; không bypass.
6. **Kiểm thử double encoding** như %252F qua môi trường có proxy thực.
7. **Kiểm thử nhiều dấu /**, semicolon, Unicode, ký tự điều khiển nếu sản phẩm nhận input tương ứng.
8. **Đảm bảo StrictHttpFirewall được dùng** và chỉ thay policy khi đã có lý do/đánh giá bảo mật.
9. **Đồng bộ MVC + security matcher**, dùng MvcRequestMatcher/HandlerMappingIntrospector phù hợp với Servlet mapping.
10. **Không mở wildcard quá rộng**, không có permitAll trước rule bảo vệ.
11. **Test denyAll fallback** cho route chưa định nghĩa; nếu chọn authenticated fallback, hiểu khi nào MVC trả 404.
12. **Thử qua reverse proxy/CDN**: URL đã forward có giống URL client dự kiến? Canonical redirects có giữ auth?
13. **Kiểm tra context path, servletPath**, sự lựa chọn giữa nhiều SecurityFilterChain.
14. **Đừng bỏ validation/business authorization** dù request đã qua HTTP authorization.
15. **Theo dõi thay đổi phiên bản:** cấu hình mặc định của MVC, Servlet container và Spring Security có thể thay đổi; lưu test làm contract.

Một bộ test chỉ có GET /route với user đúng quyền là chưa đủ. Các regression thường nằm ở **biến thể URL** hoặc **mismatch giữa những tầng xử lý**, không phải ở trường hợp chuẩn.

## 15. Tình huống tự luyện

**Câu 1.** GET /api/records/A123 khớp controller, GET /api/records/A123/ không khớp ở Spring Framework 6. Có chắc request thứ hai trả 404?

**Đáp án:** không. Nếu SecurityFilterChain có anyRequest().denyAll(), request có thể bị từ chối 403 trước MVC. 404 là trường hợp nó đi tới MVC mà không có handler.

**Câu 2.** Vì sao %2F không thể luôn được xem như dấu / thông thường?

**Đáp án:** container, firewall, proxy và MVC có thể từ chối/giải mã khác nhau. Sự khác biệt ở boundary segment có thể làm security matcher và controller hiểu URL khác.

**Câu 3.** MvcRequestMatcher giải quyết được mọi rủi ro URL encoding chưa?

**Đáp án:** chưa. Nó giúp matching dựa trên semantics của MVC, nhưng container/proxy/firewall vẫn có chính sách riêng; còn cần validation và authorization dữ liệu.

**Câu 4.** Nếu bật permitAll("/api/**") trước rule có hasRole("READER"), chuyện gì xảy ra?

**Đáp án:** rule rộng match trước có thể cho phép cả endpoint cần READER. Phải đặt rule hẹp trước và không công khai wildcard vượt ý định.

**Câu 5.** POST /api/records/A123 với role READER có được hưởng quyền từ rule GET không?

**Đáp án:** không, nếu matcher đã giới hạn HttpMethod.GET. POST có thể bị CSRF hoặc authorization fallback chặn.

**Câu 6.** Vì sao MockMvc test không thay được thử nghiệm %2F qua cổng thật?

**Đáp án:** MockMvc không chạy nguyên Servlet container và reverse proxy; các tầng đó có thể reject hoặc normalize URL trước Spring Security.

**Câu 7.** Nếu đường dẫn có hai dấu / liên tiếp, có nên tự dùng String.replace("//", "/") trong AuthorizationManager không?

**Đáp án:** không. Tự chuẩn hóa cục bộ tại Security có thể khác MVC/proxy; ưu tiên reject URL bất thường hoặc canonicalization đã được thiết kế và test chung.

**Câu 8.** Khi app triển khai dưới /shop, pattern @GetMapping có cần thêm /shop không?

**Đáp án:** thường không: context path là phạm vi triển khai, còn MVC mapping được khai báo tương đối theo application/servlet mapping. Cần kiểm thử nếu có servletPath hoặc proxy rewrite đặc biệt.

**Câu 9.** Khi reader được phép GET /api/records/{id}, người đó có quyền đọc mọi ID trong database không?

**Đáp án:** không tự động. Rule role chỉ chặn tại HTTP. Service vẫn cần kiểm tra owner/tenant/permission thật trên bản ghi.

**Câu 10.** Request encoded path nhận 400. Có chứng minh role rule đã từ chối đúng người không?

**Đáp án:** không. Có thể request bị Servlet container/StrictHttpFirewall từ chối trước authorization. Muốn kiểm tra rule phải dùng URL được framework tiếp nhận và đo đường đi xử lý.

## Kết luận

**Đường dẫn không chỉ là chuỗi ký tự:** trailing slash, percent encoding, context path, servlet mapping và reverse proxy có thể ảnh hưởng cách một request được hiểu ở nhiều tầng. Trong Spring Security Servlet, hãy dùng matcher có ngữ nghĩa tương thích với Spring MVC, ưu tiên **MvcRequestMatcher + HandlerMappingIntrospector** trong ứng dụng MVC khi phù hợp, giữ StrictHttpFirewall và quy tắc deny-by-default cho đường dẫn không được khai báo.

Khi nâng Spring Framework 6, hãy kiểm tra rõ **/route và /route/**; với encoded slash hoặc double encoding, phải kiểm tra qua HTTP stack thật và không phỏng đoán một status code. Một hệ thống an toàn là hệ thống mà **request chuẩn được cho phép đúng người, request biến thể không vượt qua policy, và tầng MVC/service vẫn kiểm tra dữ liệu thật**.
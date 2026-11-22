# HttpFirewall: đường dẫn chứa dấu chấm phẩy, dấu gạch chéo mã hóa và ký tự bất thường

## 1. Bài toán: một URL có thể được hiểu theo nhiều cách

Trong ứng dụng Spring Security chạy trên **Servlet stack** (Spring MVC, Spring Boot 3.x, Spring Security 6.x), request đi qua nhiều thành phần: reverse proxy, servlet container, bộ lọc Spring Security, bộ so khớp đường dẫn và DispatcherServlet. Chúng không nhất thiết diễn giải ký tự đặc biệt trong URL theo cùng một cách.

Ví dụ, một client gửi:

~~~http
GET /documents/a%2Fb HTTP/1.1
Host: example.test
~~~

Chuỗi **%2F** biểu diễn dấu **/** khi giải mã theo percent-encoding. Một tầng có thể xem **a%2Fb** là *một* thành phần đường dẫn; tầng khác có thể giải mã thành **a/b** rồi hiểu là *hai* thành phần. Khi logic **phân quyền** và logic **định tuyến controller** không nhìn thấy cùng một đường dẫn, hệ thống có nguy cơ áp dụng sai quy tắc bảo mật.

Các ví dụ khác:

- **/products;category=books**: dấu **;** có thể được dùng cho path parameter hoặc matrix variable. Một tầng có thể giữ phần sau dấu chấm phẩy, tầng khác có thể loại bỏ.
- **/files/a%5Cb**: **%5C** biểu diễn dấu gạch chéo ngược (backslash); một số môi trường có thể coi nó như dấu phân tách đường dẫn.
- **/files/%2e%2e/secret**: dấu chấm được percent-encode có thể tham gia tạo thành phân đoạn **..** sau khi giải mã.
- **/files/%252F**: **%25** là dấu phần trăm được mã hóa; nếu nhiều tầng giải mã hơn một lần, chuỗi có thể tiếp tục biến thành **%2F**, rồi thành **/**.
- **/files//secret**, **/files/../secret**, ký tự NUL hoặc các ký tự điều khiển: có thể được chuẩn hóa, loại bỏ hoặc từ chối tại các tầng khác nhau.

Mục đích của **HttpFirewall** là bảo vệ quá trình xử lý request của Spring Security khỏi những dạng URL hoặc HTTP request không an toàn, không chuẩn, hoặc dễ gây bất đồng khi so khớp. Không nên coi cách một URL hiển thị trong trình duyệt là bằng chứng rằng mọi tầng đã nhìn thấy chính xác cùng một chuỗi.

**Sau bài học, bạn có thể** nhận biết URL mơ hồ, hiểu lý do **StrictHttpFirewall** từ chối các nhóm ký tự nguy hiểm theo mặc định, cấu hình ngoại lệ có kiểm soát, thử nghiệm với request giả lập và request HTTP thực, và phân biệt lỗi do firewall với lỗi 401/403 trong SecurityFilterChain.

## 2. HttpFirewall nằm ở đâu?

**HttpFirewall** là interface trong Spring Security Servlet. Thành phần **FilterChainProxy** sử dụng nó để kiểm tra và bao bọc request/response trước khi chọn danh sách security filter. Trong cấu hình Spring Security thông dụng, implementation mặc định là **StrictHttpFirewall**.

~~~text
Client
  │
  ▼
Reverse proxy / gateway
  │   có thể chặn, chuyển đổi hoặc chuẩn hóa URL
  ▼
Servlet container (ví dụ Tomcat)
  │   có thể từ chối request hoặc diễn giải đường dẫn
  ▼
DelegatingFilterProxy → FilterChainProxy
  │
  ├── HttpFirewall kiểm tra và tạo FirewalledRequest
  │     ├── request không hợp lệ → RequestRejectedException
  │     └── request hợp lệ     → tiếp tục
  │
  └── chọn SecurityFilterChain phù hợp
        ▼
      Authentication / Authorization / CSRF / ...
        ▼
      DispatcherServlet → Controller
~~~

Điểm cần nhớ:

1. **Firewall xử lý trước khi so khớp SecurityFilterChain.** Một request bị từ chối tại đây sẽ không đến **requestMatchers(...)**, controller hoặc **@PreAuthorize**. Thêm **permitAll()** không làm cho URL bị StrictHttpFirewall chặn trở nên hợp lệ.
2. **HttpFirewall không đồng nghĩa với HTTP status 403.** Khi firewall từ chối, Spring Security có thể ném **RequestRejectedException**; cơ chế **RequestRejectedHandler** thường chuyển thành HTTP **400**. Tuy nhiên servlet container hoặc proxy có thể từ chối trước, nên status thực tế và log còn tùy cấu hình.
3. **Firewall không thay thế authorization.** Một URL vượt qua firewall vẫn phải thỏa quy tắc xác thực, phân quyền, CSRF và kiểm tra dữ liệu đầu vào.
4. **Firewall thấy request sau các tầng phía trước.** Nếu proxy/container đã giải mã hoặc chuẩn hóa, firewall không thể tự khôi phục chuỗi ban đầu. Chính sách đường dẫn phải nhất quán từ edge đến ứng dụng.
5. **HttpFirewall thuộc Servlet stack.** Không lấy đoạn cấu hình này để áp trực tiếp cho SecurityWebFilterChain trong WebFlux.

### Một số góc nhìn về đường dẫn

Trong Servlet API, **getRequestURI()** thường phản ánh URI request ở dạng được biểu diễn trong request, còn **getServletPath()** và **getPathInfo()** có thể mang góc nhìn khác do container và servlet mapping. Các request matcher có thể sử dụng các biểu diễn đã qua xử lý. Cụ thể cách mã hóa, giải mã và chuẩn hóa phụ thuộc container, cấu hình và phiên bản, nên không giả định hai chuỗi này luôn tương đương.

Vấn đề bảo mật cốt lõi là tránh tình huống **đường dẫn được kiểm tra quyền khác đường dẫn được thực thi**.

## 3. Những nhóm ký tự cần xem xét

| Ví dụ trong path | Vì sao cần chú ý | Hướng xử lý |
| --- | --- | --- |
| **/items;type=book** | Dấu **;** có thể là path parameter/matrix variable; các tầng có thể bỏ hoặc giữ phần sau nó | StrictHttpFirewall từ chối mặc định; nếu thật sự cần matrix variable, đánh giá ngoại lệ riêng |
| **/docs/a%2Fb** hoặc **/docs/a%2fb** | Dấu **/** được mã hóa; giải mã tạo ra ranh giới segment khác | Giữ cấu hình từ chối mặc định; ưu tiên đổi thiết kế URL |
| **/docs/a%5Cb** | Backslash có thể được một số tầng xem như slash | Giữ từ chối; không coi backslash là cách viết thay thế của dấu **/** |
| **/docs/%2e%2e/private** | Các dấu chấm có thể trở thành **..** sau giải mã, liên quan đến chuẩn hóa phân đoạn | Từ chối đường dẫn không chuẩn; không tự giải mã nhiều lượt |
| **/docs/%252F** | Mã hóa nhiều lớp tạo rủi ro cách hiểu khác nhau | Giới hạn decoding nhất quán; không nới nhiều cờ firewall để chạy được |
| **/docs//report** hoặc **/docs/../report** | Dấu phân tách lặp và dot-segment có thể được chuẩn hóa | Kiểm tra policy của container/proxy và firewall |
| **/docs/%00**, các ký tự xuống dòng/điều khiển | Có thể ảnh hưởng parsing, logging hoặc header/path handling | Từ chối, không tự chuyển thành một ID hợp lệ |
| Dấu **%** bị mã hóa không đúng, ký tự không hợp lệ | Các parser có thể trả các lỗi khác nhau | Để tầng phù hợp trả lỗi; xác định chính xác tầng từ chối khi điều tra |

**Lưu ý về các ví dụ:** Bảng trình bày rủi ro và hướng xử lý. Không phải mọi URL đều được nhìn thấy nguyên dạng bởi Spring Security; proxy hoặc container có thể trả lỗi trước. Danh sách ký tự và phương thức cụ thể mà StrictHttpFirewall chặn còn có thể khác theo phiên bản Spring Security và các cờ cấu hình. Không nên viết test end-to-end chỉ giả định một HTTP status cho mọi container.

### Tại sao dấu chấm phẩy nguy hiểm?

Một hệ thống MVC có thể muốn xử lý URL như:

~~~text
/cars;color=red;year=2026
~~~

Nhưng một bộ so khớp bảo mật có thể bỏ phần **;color=red;year=2026** khi đánh giá quy tắc, trong khi phần xử lý khác vẫn sử dụng nó. Một dạng lịch sử của path parameter là **;jsessionid=...** (URL rewriting cho session). Nếu hệ thống cho phép các cú pháp này không nhất quán, việc so khớp tài nguyên và áp chính sách truy cập có thể sai lệch.

**StrictHttpFirewall mặc định từ chối dấu chấm phẩy** để tránh lớp mơ hồ đó. Nếu không thực sự cần matrix variables, thiết kế đơn giản hơn là dùng query parameters:

~~~text
GET /cars?color=red&year=2026
~~~

Cách này giữ path rõ ràng; query parameters vẫn phải được validate ở controller/service. Không nên bật dấu chấm phẩy chỉ để làm cho một URL cũ hoạt động mà không kiểm tra toàn bộ luồng routing và security matching.

### Tại sao encoded slash đáng ngại hơn slash thông thường?

**/files/folder/report** có hai segment sau **/files** và có ý nghĩa rõ ràng. Ngược lại, **/files/folder%2Freport** cố đặt dấu slash **bên trong một segment đã mã hóa**. Nếu container giải mã trước router, nó có thể trở thành đường dẫn hai segment; nếu không, controller có thể đọc một segment chứa ký tự **/**. Các biến thể double encoding làm việc đối chiếu càng khó.

Nếu muốn truyền một **khóa dữ liệu** có slash, thường nên:
- đưa khóa đó vào query parameter và kiểm tra giá trị sau khi binding;
- dùng định dạng opaque ID an toàn với URL path như UUID hoặc Base64 URL-safe;
- hoặc thiết kế route nhiều segment rõ ràng, đồng thời kiểm tra quyền trên tài nguyên đích.

Chỉ mở **setAllowUrlEncodedSlash(true)** khi có yêu cầu bắt buộc, hiểu chính xác cách proxy/container/parser xử lý và có test chứng minh rằng routing và authorization cùng sử dụng một cách diễn giải. Cho phép ở Spring Security vẫn **không đảm bảo** Tomcat hoặc proxy cho phép URI ấy đi qua.

## 4. Cấu hình StrictHttpFirewall trong Servlet Security

Mã dưới đây minh họa chính sách **giữ mặc định nghiêm ngặt**: URL bình thường đi đến controller, các dạng đường dẫn mơ hồ do StrictHttpFirewall quyết định từ chối. Đây là một ứng dụng Spring Boot 3.x với Java 17+.

Tại dự án Gradle Spring Boot, thêm các dependency nếu chưa có:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Tạo tệp **src/main/java/com/example/firewalldemo/FirewallDemoApplication.java**:

~~~java
package com.example.firewalldemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.firewall.StrictHttpFirewall;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class FirewallDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FirewallDemoApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/public/documents/**").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    WebSecurityCustomizer webSecurityCustomizer() {
        StrictHttpFirewall firewall = new StrictHttpFirewall();
        // Giữ các mặc định nghiêm ngặt; không mở ngoại lệ đại trà.
        return web -> web.httpFirewall(firewall);
    }
}

@RestController
class DocumentController {
    @GetMapping("/public/documents/by-key")
    String byKey(@RequestParam String key) {
        return "key=" + key;
    }

    @GetMapping("/public/documents/{id}")
    String byId(@PathVariable String id) {
        return "document=" + id;
    }
}
~~~

Khi gửi **GET /public/documents/report**, request bình thường có thể đến controller và nhận body **document=report**. Nếu khóa thực là **department/2026**, client có thể dùng **GET /public/documents/by-key?key=department%2F2026**, thay vì cố đặt **%2F** trong path. Ví dụ controller chỉ minh họa binding; ứng dụng thực phải kiểm tra quyền trên khóa/tài nguyên, giới hạn đầu vào và kiểm soát quyền truy cập dữ liệu.

**Vì sao dùng WebSecurityCustomizer?** Thuộc tính **web.httpFirewall(firewall)** gắn firewall vào cấu hình **WebSecurity** quản lý FilterChainProxy. Một số cấu hình Spring Boot/Security có thể tự nhận bean HttpFirewall, nhưng cách khai báo tường minh ở ví dụ này thể hiện rõ firewall nào đang được sử dụng. Đây không phải cơ chế mở quyền trong **authorizeHttpRequests**.

### Ngoại lệ dấu chấm phẩy khi thực sự cần matrix variables

Trong một ứng dụng **bắt buộc** dùng matrix variables, có thể tạo **một** StrictHttpFirewall được cấu hình:

~~~java
StrictHttpFirewall firewall = new StrictHttpFirewall();
firewall.setAllowSemicolon(true);
~~~

Đặt hai dòng trên **thay cho** dòng khởi tạo firewall trong **webSecurityCustomizer**; không tạo thêm nhiều HttpFirewall cạnh tranh. Phải đồng thời rà soát cách Spring MVC xử lý matrix variables, cách security matcher nhận diện endpoint và cách proxy/container truyền path. Trong test, kiểm tra cùng một tài nguyên qua các dạng path tương ứng và xác minh authorization không bị thay đổi.

**Không suy rộng** rằng bật semicolon đồng thời mở encoded slash hoặc giải quyết mọi lỗi URL. Hai trường hợp thuộc các quy tắc khác nhau. Cần đặc biệt thận trọng với **setAllowUrlEncodedSlash(true)**, **setAllowBackSlash(true)** hoặc các tùy chọn liên quan percent-encoding; bật một cờ chỉ có thể tháo một lớp từ chối, trong khi các tầng khác vẫn có thể xử lý URL theo cách khác.

Đừng chuyển từ **StrictHttpFirewall** sang một firewall kém nghiêm ngặt chỉ vì gặp một test 400. Hãy xác định yêu cầu URL hợp lệ và nguy cơ của ngoại lệ trước.

## 5. Kiểm thử chính các hành vi của firewall

Có hai loại test bổ sung cho nhau:

- **Unit test trực tiếp StrictHttpFirewall**: kiểm tra quy tắc bị từ chối của implementation mà không phụ thuộc cách container chuyển đổi URI.
- **Integration test qua HTTP thật**: kiểm tra toàn bộ chuỗi proxy, container, filter và MVC. Kết quả có thể bị từ chối trước khi tới HttpFirewall, nên cần xem log để xác định tầng thực sự gây lỗi.

Tạo tệp **src/test/java/com/example/firewalldemo/FirewallPolicyTest.java**:

~~~java
package com.example.firewalldemo;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.firewall.RequestRejectedException;
import org.springframework.security.web.firewall.StrictHttpFirewall;

class FirewallPolicyTest {
    @Test
    void acceptsOrdinaryPath() {
        StrictHttpFirewall firewall = new StrictHttpFirewall();
        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", "/public/documents/report");

        assertThatCode(() -> firewall.getFirewalledRequest(request))
                .doesNotThrowAnyException();
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "/public/documents;version=2",
            "/public/documents/a%2Fb",
            "/public/documents/a%5Cb"
    })
    void rejectsAmbiguousPathsByDefault(String uri) {
        StrictHttpFirewall firewall = new StrictHttpFirewall();
        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", uri);

        assertThatThrownBy(() -> firewall.getFirewalledRequest(request))
                .isInstanceOf(RequestRejectedException.class);
    }

    @Test
    void explicitSemicolonExceptionDoesNotAlsoAllowEncodedSlash() {
        StrictHttpFirewall firewall = new StrictHttpFirewall();
        firewall.setAllowSemicolon(true);

        MockHttpServletRequest semicolonRequest =
                new MockHttpServletRequest(
                        "GET", "/public/documents;version=2");
        assertThatCode(
                () -> firewall.getFirewalledRequest(semicolonRequest))
                .doesNotThrowAnyException();

        MockHttpServletRequest encodedSlashRequest =
                new MockHttpServletRequest(
                        "GET", "/public/documents/a%2Fb");
        assertThatThrownBy(
                () -> firewall.getFirewalledRequest(encodedSlashRequest))
                .isInstanceOf(RequestRejectedException.class);
    }
}
~~~

Giải thích:

1. Path bình thường không bị StrictHttpFirewall chặn.
2. Ba trường hợp **;**, **%2F**, **%5C** được kiểm chứng bằng lỗi **RequestRejectedException** trong request giả lập ở cấu hình mặc định.
3. Khi bật **setAllowSemicolon(true)**, test về semicolon có thể đi qua firewall; **%2F** vẫn bị từ chối.
4. Unit test không chứng minh endpoint được phân quyền hay container chấp nhận URL đó. Controller và authorization chưa được gọi trong test này.

Chạy tại gốc dự án có Gradle wrapper:

~~~bash
./gradlew test --tests com.example.firewalldemo.FirewallPolicyTest
~~~

Trên Windows dùng **gradlew.bat test --tests com.example.firewalldemo.FirewallPolicyTest**. Khi toàn bộ test thành công, Gradle hiển thị kết quả build thành công; không nên gán một output HTTP cụ thể cho unit test vì nó chỉ gọi phương thức Java.

### Quan sát qua HTTP và xác định tầng từ chối

Khởi chạy ứng dụng:

~~~bash
./gradlew bootRun
~~~

Gửi một request hợp lệ:

~~~bash
curl -i 'http://localhost:8080/public/documents/report'
~~~

Với ví dụ controller và policy trên, kết quả dự kiến là HTTP **200**, body:

~~~text
document=report
~~~

Dùng **--path-as-is** để quan sát cách server xử lý path bất thường thay vì để curl tự chuẩn hóa một số dot-segment:

~~~bash
curl --path-as-is -i 'http://localhost:8080/public/documents;version=2'
curl --path-as-is -i 'http://localhost:8080/public/documents/a%2Fb'
curl --path-as-is -i 'http://localhost:8080/public/documents/a%5Cb'
~~~

Một số request có thể nhận **400** từ servlet container trước Spring Security; một số khác có thể bị **StrictHttpFirewall** từ chối khi đã vào FilterChainProxy. Cần đối chiếu HTTP response, access log của proxy/container và log Spring Security để biết điểm chặn. Trong môi trường thật, không cần ghi lại toàn bộ dữ liệu nhạy cảm hoặc header Authorization khi phân tích log.

Không dùng status 400 làm căn cứ duy nhất để khẳng định lỗi do firewall, cũng không dùng 403 làm căn cứ duy nhất để khẳng định lỗi do authorization. **RequestRejectedException** là tín hiệu trực tiếp hơn nếu request thực sự tới HttpFirewall.

## 6. Đánh giá trước khi nới lỏng StrictHttpFirewall

Trước khi đổi bất kỳ cờ **setAllow...**, hãy làm theo trình tự:

1. **Đặt câu hỏi nghiệp vụ:** endpoint có thật sự cần dấu chấm phẩy hoặc encoded slash trong *path* không? Có thể dùng query parameter, ID an toàn với URL hoặc một cấu trúc route khác không?
2. **Tái hiện request gốc:** ghi rõ raw request target, HTTP method, context path, reverse proxy, servlet mapping và mã HTTP. Thử ở đúng môi trường vì proxy/Tomcat có thể xử lý khác nhau.
3. **Tìm tầng từ chối:** phân biệt lỗi parser của proxy/container, **RequestRejectedException** của Spring Security, lỗi 404 mapping controller và lỗi 401/403 do authentication/authorization/CSRF.
4. **Đối chiếu biểu diễn path:** xác nhận các thành phần quan sát URI và path như thế nào; kiểm tra việc decode, normalize, cắt path parameter hoặc xử lý dấu gạch chéo ở mỗi tầng.
5. **Chỉ nới đúng quy tắc cần thiết:** ví dụ thật sự dùng matrix variables thì cân nhắc **setAllowSemicolon(true)**; không mở thêm encoded slash, backslash, ký tự điều khiển chỉ để tránh lỗi thử nghiệm.
6. **Kiểm thử cả trường hợp được và bị từ chối:** URL chuẩn, URL chứa ký tự đã được cho phép, các biến thể encoded, double-encoded, dấu phân tách khác thường và request không được cấp quyền. Kiểm thử chống quyền vượt phạm vi đối với tài nguyên thực, không chỉ test HTTP status.
7. **Đánh giá cấu hình triển khai:** kiểm tra proxy, WAF, phiên bản Tomcat, Spring Security, routing của MVC và các thay đổi giữa staging/production. Một thay đổi chỉ ở Spring Security không chắc đủ.
8. **Theo dõi có giới hạn:** quan sát số lượng RequestRejectedException và loại ký tự bị từ chối; tránh log hoặc hiển thị nguyên văn dữ liệu nhạy cảm từ request bất thường.

### Những lỗi tư duy cần tránh

| Nhận định sai | Điều đúng cần nhớ |
| --- | --- |
| “URL trả 400 thì phải thêm permitAll.” | Firewall/container có thể từ chối request **trước** authorization |
| “Bật setAllowUrlEncodedSlash thì mọi %2F đều sẽ chạy.” | Proxy/container vẫn có thể chặn hoặc giải mã khác; MVC cũng có quy tắc riêng |
| “Dùng URLDecoder.decode nhiều lần để sửa path.” | Giải mã lặp có thể tạo slash, dot-segment hoặc ký tự điều khiển mới; phải tránh |
| “Matrix variable chỉ là một tham số nên không ảnh hưởng bảo mật.” | Nếu tầng kiểm tra quyền và tầng định tuyến hiểu khác nhau, xuất hiện rủi ro |
| “Chuyển về DefaultHttpFirewall luôn an toàn hơn.” | Giảm chặt chẽ của firewall có thể mở lại những đường dẫn mơ hồ cần được kiểm soát |
| “Bị chặn ở firewall nghĩa là controller đã bảo mật đầy đủ.” | Controller và kiểm tra quyền chưa chạy; request hợp lệ vẫn cần authorization |
| “Đã đổi ở Spring Security nên production sẽ hành xử như unit test.” | Servlet container, proxy và môi trường triển khai là một phần của chuỗi xử lý |

## 7. Kết luận thực hành

Với đường dẫn chứa **dấu chấm phẩy**, **encoded slash** hoặc **ký tự bất thường**, câu hỏi chính không phải làm thế nào để mọi chuỗi URL đều được chấp nhận, mà là liệu **mọi tầng có diễn giải và kiểm tra cùng một tài nguyên hay không**.

Chính sách mặc định của **StrictHttpFirewall** là điểm khởi đầu an toàn. Trường hợp thật sự cần ngoại lệ, phải thu hẹp đúng loại ký tự, kiểm chứng route/authorization ở cả Servlet container và Spring Security, rồi bổ sung test âm cho các biến thể vẫn phải bị từ chối. Dùng URL path đơn giản, ID ổn định và phân quyền trên tài nguyên đã được xác định rõ thường dễ bảo vệ hơn việc nới lỏng firewall để chấp nhận mọi cách mã hóa đường dẫn.

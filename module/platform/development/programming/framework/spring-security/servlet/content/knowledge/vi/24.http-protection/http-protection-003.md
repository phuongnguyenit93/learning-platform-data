# Strict-Transport-Security, HTTPS và điều kiện bật HSTS trong Spring Security Servlet

## 1. HTTPS bảo vệ kết nối; HSTS bảo vệ việc chọn kết nối HTTPS

**HTTPS** dùng TLS để mã hóa và xác thực kết nối giữa trình duyệt và máy chủ. Nếu người dùng truy cập đúng URL HTTPS và kiểm tra chứng chỉ thành công, người đứng giữa không thể tùy ý đọc hoặc sửa nội dung ứng dụng trên kết nối đó. Nhưng HTTPS tự nó không buộc trình duyệt luôn chọn HTTPS vào những lần sau: người dùng có thể nhập địa chỉ không có giao thức, mở liên kết bắt đầu bằng http:// hoặc bị chuyển tới HTTP trước khi máy chủ trả hướng dẫn chuyển sang HTTPS.

**HTTP Strict Transport Security (HSTS)** là cơ chế để một website thông báo cho trình duyệt: *trong khoảng thời gian xác định, mọi kết nối tiếp theo đến tên miền này phải dùng HTTPS*. Máy chủ đưa chính sách vào HTTP response header **Strict-Transport-Security** trên một kết nối HTTPS hợp lệ. Trình duyệt hỗ trợ HSTS lưu chính sách đó và tự nâng cấp những lần truy cập HTTP sau này, trước khi gửi request qua mạng.

HSTS giúp giảm rủi ro hạ cấp từ HTTPS xuống HTTP và một số cuộc tấn công chặn, sửa redirect (SSL stripping). Nó **không thay thế** chứng chỉ TLS hợp lệ, chuyển hướng HTTP sang HTTPS, cấu hình TLS an toàn, cookie Secure, CSRF, xác thực hay phân quyền. Trong ứng dụng Spring Security **Servlet** (Spring MVC), HSTS thuộc nhóm security response headers do Spring Security có thể tự sinh.

Mục tiêu bài học:

- Hiểu quy trình trình duyệt ghi nhớ và áp dụng chính sách HSTS.
- Đọc đúng các directive **max-age**, **includeSubDomains** và **preload**.
- Biết lúc nào Spring Security gửi header, đặc biệt khi TLS kết thúc tại reverse proxy.
- Cấu hình và kiểm thử HSTS cho ứng dụng Spring Boot 3.x / Spring Security 6.x.
- Đánh giá điều kiện hạ tầng trước khi bật HSTS dài hạn, bao gồm kế hoạch hoàn tác.

## 2. Header Strict-Transport-Security hoạt động như thế nào?

Một phản hồi HTTPS có thể mang header:

~~~http
HTTP/1.1 200 OK
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Type: text/html; charset=UTF-8
~~~

Khi nhận header qua kết nối TLS hợp lệ, trình duyệt có hỗ trợ HSTS ghi nhớ chính sách đối với **hostname** của response. Ví dụ truy cập https://app.example.com lần đầu và nhận header ở trên, trình duyệt ghi nhớ rằng app.example.com và các tên miền con trực thuộc nó phải truy cập bằng HTTPS trong khoảng một năm kể từ lúc chính sách được cập nhật.

Luồng đơn giản:

~~~text
Lần đầu (chưa có chính sách HSTS trong trình duyệt):
Người dùng -> http://app.example.com
           -> server trả 301/308 sang https://app.example.com
           -> TLS bắt tay, xác minh chứng chỉ
           <- HTTPS response có Strict-Transport-Security
           -> trình duyệt lưu chính sách cho app.example.com

Lần sau (chính sách vẫn còn hiệu lực):
Người dùng -> http://app.example.com
           -> trình duyệt tự đổi sang https://app.example.com
           -> chỉ khởi tạo kết nối HTTPS; không gửi HTTP request đầu tiên
~~~

Phân biệt hai hành động:

1. **Redirect HTTP → HTTPS** là chỉ dẫn từ máy chủ (ví dụ 301 hoặc 308). Để nhận redirect, client thường đã phải kết nối HTTP ít nhất một lần nếu chưa có HSTS.
2. **HSTS upgrade** được trình duyệt thực hiện ngay khi xác định URL trước khi gửi request. Không cần nhận redirect mới từ server ở lần truy cập đó.

**Giới hạn lần truy cập đầu:** nếu trình duyệt chưa từng biết HSTS của tên miền và tên miền không có trong danh sách preload của trình duyệt, một request HTTP ban đầu vẫn có thể bị can thiệp trước khi trình duyệt nhận HTTPS response hợp lệ. Vì vậy, HSTS sau khi học chính sách giúp bảo vệ những lần sau; preload là cơ chế tùy chọn có thể giảm khoảng trống này đối với trình duyệt có sẵn danh sách.

Trình duyệt chỉ chấp nhận chính sách HSTS gửi trên **HTTPS tin cậy**. Header xuất hiện trên response HTTP thuần bị bỏ qua cho mục đích tạo/cập nhật chính sách HSTS. Một response HTTPS có lỗi chứng chỉ cũng không phải kênh đáng tin để kích hoạt hoặc hủy chính sách. Việc đơn thuần phát header trên HTTP không khiến trang trở thành an toàn.

## 3. Giải thích chính xác các directive

Cú pháp điển hình:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

| Directive | Tác dụng | Cách suy xét |
| --- | --- | --- |
| **max-age=seconds** | Thời gian tối đa, tính bằng **giây**, trình duyệt phải coi hostname là HSTS host kể từ khi nhận chính sách hợp lệ. | max-age=300 là 5 phút; 86400 là 1 ngày; 31536000 xấp xỉ 1 năm. |
| **includeSubDomains** | Áp dụng cả hostname được chỉ định và **mọi tên miền con** bên dưới hostname đó. | Chỉ bật sau khi kiểm kê và đảm bảo HTTPS hoạt động cho các tên miền con trong phạm vi. |
| **preload** | Tín hiệu phục vụ quy trình đăng ký danh sách HSTS preload của các trình duyệt hỗ trợ. | Chỉ thêm khi toàn bộ hạ tầng đáp ứng yêu cầu preload và tổ chức chủ động muốn đăng ký; thêm chữ này **không tự động** đưa tên miền vào danh sách. |

Chi tiết cần nhớ:

- **max-age=0** là yêu cầu xóa chính sách HSTS đã học cho hostname gửi header, **chỉ khi trình duyệt nhận nó qua HTTPS hợp lệ**. Nó không tự xóa chính sách HSTS riêng mà từng tên miền con đã thiết lập, cũng không có nghĩa lập tức loại bỏ một tên miền đang nằm trong danh sách preload.
- Khi nhận lại header hợp lệ với max-age dương, trình duyệt **làm mới thời gian hiệu lực**. max-age không phải số giây tính từ lúc website deploy.
- Chính sách áp dụng theo **hostname**, không giới hạn ở endpoint, đường dẫn /login, /admin hay từng SecurityFilterChain. Nếu header đến từ app.example.com thì không mặc nhiên áp dụng cho tên miền cha example.com hoặc tên miền ngang hàng api.example.com.
- Header có includeSubDomains tại **example.com** bao trùm app.example.com, api.example.com và các tên miền sâu hơn. Header có includeSubDomains tại **app.example.com** bao trùm nội bộ phía dưới app.example.com, không bao trùm api.example.com.
- HSTS không được thiết kế như một chính sách theo từng port hoặc path. Trình duyệt đổi URL HTTP thành HTTPS theo quy tắc HSTS; port 80 mặc định thường chuyển sang 443, trong khi port khác có thể được giữ nguyên. Đừng dùng HSTS như một giải pháp chuyển port tùy ý.
- HSTS chủ yếu dành cho tên miền DNS; các trình duyệt không dựa vào HSTS trên địa chỉ IP literal như với một hostname thông thường. Với localhost hoặc môi trường dev, đừng lấy hành vi riêng của trình duyệt làm bằng chứng policy trên production domain.
- Một số client HTTP ngoài trình duyệt không lưu/áp dụng HSTS. Cấu hình client, reverse proxy và API vẫn phải yêu cầu HTTPS độc lập với HSTS.

Nếu trình duyệt đã lưu HSTS mà máy chủ sau đó có chứng chỉ không hợp lệ hoặc HTTPS ngừng phục vụ, trình duyệt có thể **không cho người dùng bỏ qua lỗi chứng chỉ**. Đây là lợi ích bảo mật nhưng cũng là nguy cơ vận hành nếu bật HSTS khi hạ tầng chưa sẵn sàng.

## 4. Khi nào Spring Security gửi HSTS?

Trong Spring Security 6.x trên Servlet, khi security headers mặc định vẫn hoạt động, Spring Security dùng **HstsHeaderWriter** để xuất Strict-Transport-Security trên request được nhận diện là **secure** (HTTPS). Chính sách mặc định phổ biến của Spring Security là:

~~~http
Strict-Transport-Security: max-age=31536000 ; includeSubDomains
~~~

Giá trị trên tương ứng khoảng một năm và bao gồm các subdomain; dấu cách ở định dạng hiển thị không làm thay đổi ý nghĩa. Không cần thêm cấu hình chỉ để có default header nếu headers mặc định đang được bật, request thực sự được nhận diện là secure và response đi qua security filter chain chứa header writer.

Đây là điểm dễ hiểu nhầm:

**HSTS response header không tự bật TLS cho server.** Ứng dụng chỉ phát header trên HTTPS khi Spring Security biết request đang an toàn. Nếu ứng dụng tiếp nhận HTTP và không có chuyển hướng riêng, client vẫn có thể gọi HTTP khi chưa có policy HSTS.

**HSTS response header không phải HTTPS redirect.** Muốn tất cả request HTTP được đưa sang HTTPS, cấu hình redirect tại reverse proxy/load balancer hoặc yêu cầu secure channel ở Spring Security. Chọn nơi thực hiện phù hợp với kiến trúc.

**HSTS response header cần áp dụng nhất quán trên hostname.** Nếu có nhiều SecurityFilterChain, servlet filter khác hoặc reverse proxy sinh response trước khi vào Spring Security, kiểm tra endpoint nào thực sự trả header. Một hostname có thể có trang đăng nhập, trang tĩnh, lỗi 4xx/5xx, redirect và API do nhiều thành phần phục vụ.

**HSTS default includeSubDomains không đồng nghĩa bạn đã kiểm tra mọi subdomain.** Vì vậy policy mặc định về mặt kỹ thuật có thể mạnh hơn độ sẵn sàng hạ tầng, nhất là khi cùng domain chứa các ứng dụng/khách hàng khác. Cần quyết định rõ chính sách cho tên miền triển khai trước khi phát header rộng rãi.

## 5. Ví dụ Spring Boot 3.x / Spring Security 6.x: cấu hình thận trọng

Ví dụ dưới dùng Java 17+, các dependency Spring Boot Web và Spring Security. Ứng dụng mở GET /status và cấu hình **max-age ngắn 300 giây, chưa bật includeSubDomains** để thử nghiệm. Tạo file src/main/java/demo/hsts/HstsDemoApplication.java:

~~~java
package demo.hsts;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class HstsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(HstsDemoApplication.class, args);
    }

    @GetMapping(value = "/status", produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> status() {
        return Map.of("status", "ok");
    }
}

@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/status").permitAll()
            .anyRequest().authenticated()
        );

        http.headers(headers -> headers
            .httpStrictTransportSecurity(hsts -> hsts
                .maxAgeInSeconds(300)
                .includeSubDomains(false)
            )
        );

        return http.build();
    }
}
~~~

Ý nghĩa:

- **@SpringBootApplication** khởi động ứng dụng; controller nhận GET /status và trả JSON. **SecurityConfig** nằm cùng package để được component scan phát hiện.
- **SecurityFilterChain** quản lý request tới ứng dụng; ví dụ chỉ mở /status để kiểm chứng header, không hàm ý tất cả endpoint ứng dụng thực tế phải permitAll.
- **http.headers(...httpStrictTransportSecurity(...))** thay giá trị cấu hình HSTS mặc định bằng 300 giây và tắt includeSubDomains. Spring Security vẫn chỉ viết header cho request được xem là HTTPS.
- Ví dụ này **không cấu hình TLS listener hoặc chuyển hướng HTTP**. Để chạy qua HTTPS thật, phải có TLS trên ứng dụng hoặc ở một reverse proxy. Không dùng việc gọi http://localhost:8080/status mà thiếu header để kết luận cấu hình HSTS hỏng.

Sau giai đoạn đánh giá và khi điều kiện hạ tầng đạt yêu cầu, có thể chuyển sang chính sách dài hơn:

~~~java
http.headers(headers -> headers
    .httpStrictTransportSecurity(hsts -> hsts
        .maxAgeInSeconds(31536000)
        .includeSubDomains(true)
    )
);
~~~

Đây là **đoạn thay thế phần cấu hình HSTS ở trên**, không phải một chương trình Java đứng riêng. Không nâng max-age lên một năm và bật includeSubDomains chỉ vì các request của một endpoint đã vượt qua test đơn vị.

Khi không muốn custom HSTS, có thể bỏ đoạn **http.headers(...)**; Spring Security dùng header policy mặc định nếu chưa bị tắt/thay thế. Không gọi headers.disable() chỉ để xử lý vấn đề HTTPS: thao tác đó loại bỏ nhiều security headers khác, không riêng HSTS.

## 6. Kiểm thử hành vi Spring Security tại lớp Servlet

Với spring-boot-starter-test, kiểm thử MockMvc xác nhận rằng policy chỉ được ghi vào request HTTPS và không xuất hiện trên HTTP. Tạo file src/test/java/demo/hsts/HstsHeaderTest.java:

~~~java
package demo.hsts;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HstsHeaderTest {

    @Autowired
    MockMvc mvc;

    @Test
    void httpsResponseContainsConfiguredHsts() throws Exception {
        mvc.perform(get("/status").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Strict-Transport-Security",
                containsString("max-age=300")));
    }

    @Test
    void plainHttpResponseDoesNotSetHsts() throws Exception {
        mvc.perform(get("/status").secure(false))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist("Strict-Transport-Security"));
    }
}
~~~

**MockMvc.secure(true)** mô phỏng Servlet request được đánh dấu secure; nó kiểm tra cách Spring Security tạo response header, **không thực hiện TLS handshake thật** và không chứng minh trình duyệt đã lưu chính sách. Với mã ví dụ ở phần trước, GET /status được permitAll nên hai request đều có status 200; chỉ HTTPS response có HSTS. Trong môi trường thực tế nên kiểm tra thêm includeSubDomains có mặt hay vắng mặt đúng như policy đã chọn.

Để xác nhận ngoài ứng dụng, chạy trên hostname có HTTPS và chứng chỉ hợp lệ rồi kiểm tra response:

~~~bash
curl -sSI https://app.example.com/status
curl -sSI http://app.example.com/status
~~~

Dòng lệnh thứ nhất nên cho thấy Strict-Transport-Security theo policy đã triển khai; dòng thứ hai trong production thường trả **301 hoặc 308 sang HTTPS**. Header HSTS trên response HTTP thuần, kể cả có xuất hiện, sẽ bị trình duyệt bỏ qua khi cập nhật HSTS policy.

Lưu ý **curl không mặc nhiên mô phỏng toàn bộ trạng thái HSTS của trình duyệt**. Để quan sát cơ chế nâng cấp URL, dùng trình duyệt thực với một hostname thử nghiệm, kiểm tra Developer Tools → Network/Security và trạng thái kết nối sau khi đã nhận header hợp lệ. Tránh dùng tên miền production với max-age dài cho thí nghiệm vì trình duyệt có thể giữ chính sách lâu ngay cả khi bạn đã xóa cấu hình máy chủ.

## 7. Triển khai sau reverse proxy / load balancer có TLS termination

Trong nhiều ứng dụng Spring Boot, TLS kết thúc tại Nginx, ingress, API gateway hoặc load balancer:

~~~text
Trình duyệt --HTTPS/TLS--> Reverse proxy --HTTP nội bộ--> Spring Boot
                    chứng chỉ TLS ở đây      Servlet request
~~~

Tại biên mạng, client thật sự đã dùng HTTPS; nhưng nếu proxy gọi backend bằng HTTP, container Servlet có thể thấy **request.isSecure() = false**. Vì HstsHeaderWriter chỉ xuất header cho request secure, Spring Security có thể **không gửi HSTS dù trình duyệt đang truy cập HTTPS**.

Hai mô hình phổ biến:

### Cách A — phát HSTS tại biên HTTPS

Reverse proxy là nơi biết chính xác kết nối với trình duyệt có phải HTTPS hay không. Nó cấu hình HSTS trực tiếp trên response HTTPS gửi ra ngoài, đồng thời thực hiện chuyển hướng từ HTTP sang HTTPS. Cách này thường phù hợp khi nhiều ứng dụng dùng chung ingress và có chính sách hostname nhất quán.

Yêu cầu kiểm tra: header phải xuất hiện trên các response HTTPS phù hợp, bao gồm redirect và response lỗi quan trọng; HTTP listener không được quảng bá một policy HSTS có ý nghĩa sai; chính sách tại proxy không trùng/mâu thuẫn với header do ứng dụng tự phát. Các reverse proxy có cú pháp khác nhau cho việc phát header ở mọi mã trạng thái.

### Cách B — để Spring Security phát HSTS dựa trên thông tin proxy đáng tin

Proxy có thể chuyển thông tin về scheme gốc qua **Forwarded** hoặc **X-Forwarded-Proto**. Spring Boot hỗ trợ xử lý forwarded headers bằng chiến lược framework hoặc native phù hợp. Một thiết lập thường gặp:

~~~properties
server.forward-headers-strategy=framework
~~~

Khi triển khai cách này, proxy/load balancer **phải loại bỏ hoặc ghi đè Forwarded/X-Forwarded-* do client bên ngoài tự gửi**, rồi gán các header phản ánh đúng kết nối thực tế. Backend phải giới hạn đường truy cập để client không thể trực tiếp giả mạo các header đó. Nếu không bảo vệ trust boundary này, ứng dụng có thể hiểu nhầm nguồn request và phát sinh lỗi redirect, tạo URL, cookie hoặc kiểm soát security.

Kiểm tra bằng cách gửi HTTPS thực qua đúng đường ingress, rồi xem response client nhận có HSTS hay chưa; đồng thời kiểm tra container đã nhận đúng scheme. Không giả định request.isSecure() sẽ tự đổi thành true chỉ vì proxy đã gắn X-Forwarded-Proto, nếu container/framework chưa xử lý.

**Quy tắc vận hành:** chọn một nơi làm chủ policy cho mỗi hostname (proxy hoặc ứng dụng) và xác minh toàn bộ đường trả response. Nhiều tầng thêm các giá trị HSTS không đồng nhất có thể gây khó chẩn đoán; không dựa vào thứ tự header trùng để quyết định chính sách.

## 8. HTTPS redirect, yêu cầu secure channel và HSTS là ba việc liên quan

| Cơ chế | Thực hiện ở đâu? | Tác dụng |
| --- | --- | --- |
| TLS/certificate | Server hoặc TLS-terminating proxy | Mã hóa kết nối và chứng minh danh tính máy chủ. |
| HTTP → HTTPS redirect | Proxy/server hoặc Spring Security channel rules | Dẫn client từ URL HTTP sang HTTPS sau khi client gửi request. |
| HSTS | Browser sau khi nhận header HTTPS hợp lệ | Tự nâng cấp các lần truy cập tới hostname HSTS mà không bắt đầu bằng HTTP. |

Một cách yêu cầu secure channel trong Spring Security Servlet 6.x là:

~~~java
http.requiresChannel(channels -> channels
    .anyRequest().requiresSecure()
);
~~~

Đây là đoạn cấu hình bổ sung trong SecurityFilterChain, không thay cho TLS server hay HSTS. Khi nhận request HTTP, Spring Security có thể chuyển hướng sang HTTPS theo quy tắc channel đã cấu hình. Nhưng nếu proxy đã terminate TLS và backend vẫn hiểu request là HTTP, áp dụng requiresSecure() mà không cấu hình forwarded headers đúng có thể gây **vòng lặp redirect**.

Đối với hệ thống có TLS ở ingress, thường nên để ingress chịu trách nhiệm HTTPS redirect, và để ứng dụng tập trung vào security headers, xác thực, authorization. Dù chọn nơi nào, vẫn cần xác minh trực tiếp hai URL từ bên ngoài:

- http://app.example.com/... dẫn sang https://app.example.com/... đúng host/path, đúng HTTP status.
- https://app.example.com/... cung cấp chứng chỉ tin cậy, TLS phù hợp và HSTS policy mong muốn.

HTTP redirect dù là 301/308 vẫn không bảo vệ lần đầu trước kẻ can thiệp đường truyền; HSTS đã học hoặc preload mới giảm rủi ro đó tại trình duyệt.

## 9. Điều kiện cần đánh giá trước khi bật HSTS trên production

### 9.1. HTTPS thật sự sẵn sàng

Mọi request HTTPS tới hostname cần được phục vụ ổn định với chứng chỉ hợp lệ, đầy đủ intermediate chain, SAN phù hợp tên miền, tự động gia hạn chứng chỉ đáng tin, phiên bản/giao thức TLS được hỗ trợ, và không có đường lỗi buộc người dùng quay về HTTP. Kiểm tra cả trang đăng nhập, static assets, API, file download, trang lỗi và URL redirect.

Nếu HTTPS mất khả dụng sau khi trình duyệt lưu HSTS, người dùng có thể bị khóa khỏi website đến khi khắc phục chứng chỉ/TLS hoặc policy hết hạn. Không thể tin rằng chỉ cần trả HTTP response hay gửi max-age=0 qua HTTP là cứu được các trình duyệt đang giữ chính sách.

### 9.2. Tất cả hostname trong phạm vi includeSubDomains đều dùng được HTTPS

Tại example.com, bật includeSubDomains ảnh hưởng tới **mọi** subdomain, kể cả tài sản không nằm trong repository ứng dụng này: api.example.com, mail/webmail, trang hỗ trợ, legacy host, tên miền nội bộ truy cập từ browser, tên miền môi trường thử nghiệm hoặc các dịch vụ do đơn vị khác quản lý. Phải kiểm kê DNS và owner của từng host liên quan, xác nhận TLS/certificate cho mỗi dịch vụ cần hoạt động qua trình duyệt.

Đặc biệt, HSTS ở app.example.com không giúp che lỗi HTTPS tại api.example.com nếu chúng là tên miền ngang cấp; chính sách chỉ áp dụng từ đúng host đã phát header trở xuống. Không dựa vào một chứng chỉ wildcard như bằng chứng rằng mọi dịch vụ đều được triển khai HTTPS tốt.

### 9.3. Redirect và mọi tuyến proxy nhất quán

Kiểm tra HTTP listener trả redirect đúng; HTTPS listener trả header đúng; CDN, ingress, web server, application và cache không bỏ header ở những response cần bảo vệ. Với nhiều host, môi trường preview hoặc shared domain, đừng áp dụng mặc định một HSTS policy rộng trên toàn bộ domain nếu chưa có quyền kiểm soát mọi subdomain.

### 9.4. Vận hành được việc gia hạn và khôi phục TLS

Phải có cảnh báo trước khi chứng chỉ hết hạn, giám sát kết nối TLS từ bên ngoài và khả năng sửa DNS/cert/ingress trong sự cố. Khi sử dụng includeSubDomains, một host cũ chỉ hỗ trợ HTTP có thể không truy cập được từ browser đã học chính sách; cần chuẩn bị đường chuyển đổi trước khi bật.

### 9.5. Chính sách phải phù hợp mức rủi ro của môi trường

Với môi trường phát triển dùng host thử nghiệm hoặc dịch vụ HTTPS chưa ổn định, không áp dụng ngay max-age nhiều năm hay preload. Với production ổn định, có thể bắt đầu bằng giá trị ngắn và tăng dần sau kiểm tra. Một kế hoạch ví dụ:

| Giai đoạn | Header minh họa | Mục đích |
| --- | --- | --- |
| Thử nghiệm | max-age=300 | Kiểm tra chính sách có đến browser trên HTTPS và không làm sai luồng. |
| Quan sát | max-age=86400 | Duy trì 1 ngày, theo dõi chứng chỉ, lỗi redirect và khách hàng. |
| Ổn định | max-age=31536000 | Duy trì khoảng 1 năm sau khi bảo đảm hạ tầng và quy trình khôi phục. |
| Phạm vi mở rộng | Thêm includeSubDomains sau kiểm kê | Chỉ tăng phạm vi khi mọi subdomain chịu tác động đã sẵn sàng. |
| Preload (tùy chọn) | includeSubDomains và preload, đáp ứng chính sách đăng ký | Yêu cầu cam kết lâu dài với toàn domain và quy trình gỡ phức tạp. |

Các mốc là **phương án rollout minh họa**, không phải chuỗi thời gian bắt buộc hoặc bảo đảm an toàn. Độ dài max-age và mức bao phủ phải do owner tên miền và hạ tầng chấp thuận dựa trên bằng chứng kiểm thử.

## 10. Preload: lợi ích và chi phí duy trì

Preload đưa chính sách HSTS của tên miền vào danh sách được phân phối sẵn trong các trình duyệt tham gia, giúp trình duyệt nâng cấp kết nối ngay cả khi người dùng **chưa từng** vào website trước đó. Khả năng này có ích để thu hẹp rủi ro "lần truy cập đầu".

Header ví dụ sau cho thấy ý định preload:

~~~http
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
~~~

Nhưng **thêm preload vào header không đồng nghĩa đã được preload**. Quá trình đăng ký yêu cầu đáp ứng các tiêu chí của hệ sinh thái HSTS preload (HTTPS hợp lệ, redirect, max-age tối thiểu, includeSubDomains, cú pháp header và các điều kiện hiện hành), gửi đăng ký và chờ danh sách trình duyệt cập nhật. Các tiêu chí cụ thể có thể thay đổi; trước khi nộp, đọc yêu cầu hiện hành tại https://hstspreload.org và chỉ thực hiện khi tổ chức quản lý cả domain, subdomain và vòng đời chứng chỉ.

Các hệ quả:

- Domain và mọi subdomain bị buộc HTTPS bởi browser hỗ trợ preload, kể cả với khách truy cập mới. Một subdomain HTTP cũ có thể ngừng truy cập.
- Nếu muốn rút tên miền khỏi preload, cần đi qua quy trình removal và chờ các phiên bản trình duyệt phân phối danh sách mới; không bảo đảm có hiệu lực ngay khi đổi header.
- Nếu HTTPS/certificate hỏng, client đã preload có thể không có lối bypass. Hãy coi preload là quyết định thay đổi phạm vi nhiều dịch vụ và có vòng đời dài.

Preload không bắt buộc chỉ để có HSTS thông thường. Một website có thể bảo vệ các lần truy cập tiếp theo bằng max-age dương mà không đăng ký preload.

## 11. Gỡ hoặc giảm HSTS khi cần thay đổi chính sách

Nếu chưa preload, và bạn kiểm soát được HTTPS trên hostname, có thể trả:

~~~http
Strict-Transport-Security: max-age=0
~~~

qua **HTTPS hợp lệ** để yêu cầu browser xóa HSTS policy của chính hostname đó. Nếu muốn giữ policy nhưng thu hẹp thời hạn, phát max-age mới nhỏ hơn trên HTTPS; nếu muốn bỏ includeSubDomains, phát chính sách mới không còn directive này, sau đó đánh giá các child hosts có policy HSTS riêng.

Thao tác gỡ gặp các giới hạn thực tế:

1. Browser chỉ nhận chỉ thị cập nhật khi kết nối HTTPS được xác minh thành công; nếu chứng chỉ đã hỏng, cần **sửa TLS trước**.
2. Browser không truy cập lại hostname thì không nhận được chính sách mới; trạng thái cũ tiếp tục tồn tại cho tới khi hết hạn hoặc được cập nhật.
3. max-age=0 tại example.com không tự xóa HSTS entry mà api.example.com đã gửi riêng.
4. Preloaded domain cần thêm quy trình gỡ khỏi danh sách preload và thời gian cập nhật các browser liên quan.

Không nên coi đổi max-age=0 trong config như một tính năng rollback tức thời cho mọi máy khách. Giữ đường phục vụ HTTPS hoạt động trong quá trình chuyển đổi.

## 12. Các lỗi phổ biến

**Lỗi 1 — Thấy HTTPS hoạt động nhưng không có HSTS.** Kiểm tra request có đi qua Spring Security HeaderWriterFilter không, cấu hình headers có bị disable không, request.isSecure() có đúng khi đi qua proxy không, hoặc HSTS thực tế được phát ở edge thay vì backend. Kiểm tra response cuối ở phía client, không chỉ ở localhost.

**Lỗi 2 — Thêm Strict-Transport-Security trên HTTP.** Browser bỏ qua policy từ kết nối HTTP. Bắt đầu bằng chứng chỉ TLS đúng, redirect HTTP tới HTTPS và chỉ dùng HTTPS response hợp lệ để thiết lập policy.

**Lỗi 3 — Bật includeSubDomains ngay ở domain gốc.** Có thể khóa các website con không hỗ trợ TLS. Kiểm kê toàn bộ hostname/subdomain trước khi mở rộng phạm vi, bao gồm hệ thống không cùng đội vận hành.

**Lỗi 4 — Nghĩ HSTS tương đương redirect.** HSTS không cấp chứng chỉ, không mở cổng 443 và không tự sửa mọi URL server-side. Lần đầu chưa có policy vẫn cần HTTPS redirect an toàn tại proxy/app.

**Lỗi 5 — Bật requiresSecure() sau proxy mà không xử lý forwarded headers.** Backend tưởng mọi request là HTTP và lặp redirect sang HTTPS. Đặt trust boundary và cấu hình forwarded strategy chính xác; kiểm tra đường thực tế từ browser.

**Lỗi 6 — Đánh giá bằng MockMvc rồi kết luận production an toàn.** MockMvc chỉ xác nhận xử lý header trên request giả lập. Chứng chỉ, 301/308, proxy, CDN, các host và ứng xử browser thực phải được kiểm tra ngoài ứng dụng.

**Lỗi 7 — Dùng preload làm checkbox cấu hình.** Header directive preload không tự đăng ký; sau khi đã đăng ký, gỡ bỏ chậm và cần kiểm soát toàn bộ subdomain. Chỉ nộp khi đủ điều kiện lâu dài.

**Lỗi 8 — Đoạn response lỗi không có HSTS hoặc có nhiều header mâu thuẫn.** Response có thể sinh ở CDN/gateway trước khi Spring Security xử lý; kiểm tra 3xx/4xx/5xx trên HTTPS. Dùng một policy owner cho hostname và giám sát response thực.

**Lỗi 9 — Cho rằng HSTS sửa mọi vấn đề bảo mật web.** HSTS không chống XSS, CSRF, SQL injection, token lộ trong ứng dụng, hay mixed content tải từ một hostname không thuộc phạm vi HSTS. Tiếp tục áp dụng CSP, Secure/HttpOnly/SameSite cookie theo nhu cầu, authorization và security headers khác.

## 13. Checklist trước khi quyết định bật dài hạn

- [ ] TLS/certificate hợp lệ trên hostname và các tuyến HTTPS chính; có giám sát và gia hạn tự động.
- [ ] HTTP listener chuyển sang HTTPS đúng host/path; xác định rõ nơi sở hữu redirect và nơi phát HSTS.
- [ ] Kiểm tra browser nhận Strict-Transport-Security **qua HTTPS**, đúng max-age, đúng phạm vi includeSubDomains.
- [ ] Nếu có reverse proxy/TLS termination, request scheme được tin cậy hoặc HSTS được phát tại edge; chặn forwarded headers giả mạo.
- [ ] Với includeSubDomains, đã kiểm kê host và dịch vụ chịu ảnh hưởng và xác nhận mọi host cần truy cập qua browser đều dùng HTTPS.
- [ ] Có kế hoạch tăng max-age từng bước, theo dõi lỗi và hướng xử lý certificate/HTTPS khi khẩn cấp.
- [ ] Nếu chọn preload, đã kiểm tra tiêu chí hiện hành, toàn bộ domain/subdomain và thời gian gỡ qua browser list.
- [ ] Có integration test header và phép thử thực tế trên ingress/proxy; không coi test secure(true) là TLS end-to-end.

**Ghi nhớ:** HTTPS thiết lập kết nối an toàn ở thời điểm hiện tại; **HSTS yêu cầu trình duyệt tiếp tục chọn HTTPS cho hostname trong tương lai**. Spring Security Servlet có thể tự phát Strict-Transport-Security trên request secure, nhưng cấu hình TLS, redirect, reverse proxy, subdomain, thời hạn chính sách và khả năng khôi phục quyết định việc HSTS có an toàn khi triển khai hay không.

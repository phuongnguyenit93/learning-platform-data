# Cấu hình CORS toàn cục qua RepositoryRestConfigurer và CorsRegistry

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vì sao trình duyệt áp dụng same-origin policy và khi nào cần CORS.
- Hiểu origin gồm scheme, host và port.
- Phân biệt preflight request với request thực tế.
- Cấu hình CORS cho các repository resource bằng RepositoryRestConfigurer và CorsRegistry.
- Chọn allowedOrigins, allowedMethods, allowedHeaders, exposedHeaders, allowCredentials và maxAge.
- Phân biệt cấu hình toàn cục với @CrossOrigin ở phạm vi hẹp.
- Kết hợp CORS với Spring Security và kiểm tra response header bằng curl.
- Tránh dùng CORS như một cơ chế authentication hoặc authorization.

## 1. CORS giải quyết vấn đề gì?

Trình duyệt áp dụng **same-origin policy** để giới hạn cách một trang web đọc dữ liệu từ origin khác. Một origin được xác định bởi ba thành phần:

- **Scheme**: giao thức, ví dụ http hoặc https.
- **Host**: tên miền hoặc địa chỉ máy chủ.
- **Port**: cổng kết nối.

Ví dụ:

~~~text
Frontend: https://app.example.com
API:      https://api.example.com
~~~

Hai địa chỉ trên có host khác nhau nên là hai origin khác nhau. Khi JavaScript từ frontend gọi API, trình duyệt kiểm tra chính sách **Cross-Origin Resource Sharing (CORS)** trong response của API để quyết định có cho JavaScript đọc response hay không.

CORS là cơ chế ở phía trình duyệt dựa trên các HTTP header do server trả về. Server khai báo origin nào được phép truy cập, method nào được phép dùng, request header nào được phép gửi và response header nào JavaScript được đọc.

CORS không ngăn mọi client khác gọi API. curl, ứng dụng backend hoặc một chương trình HTTP bất kỳ không tự áp dụng same-origin policy của trình duyệt. Vì vậy CORS không thay thế authentication, authorization, CSRF protection hay validation dữ liệu.

## 2. Khi nào request cần preflight?

Một số cross-origin request có thể được gửi trực tiếp theo quy tắc CORS. Với request không thuộc nhóm đơn giản, trình duyệt gửi một **preflight request** bằng method OPTIONS để hỏi server trước khi gửi request thực tế.

Ví dụ frontend gửi POST với Content-Type application/json và header Authorization. Trình duyệt có thể gửi trước:

~~~http
OPTIONS /api/people HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization, content-type
~~~

Server trả các header cho biết request có được phép hay không:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
Access-Control-Allow-Headers: authorization, content-type
Access-Control-Max-Age: 3600
Vary: Origin
~~~

Nếu preflight được chấp nhận, trình duyệt mới gửi POST thực tế. Nếu server không cho phép origin, method hoặc header được yêu cầu, trình duyệt chặn request thực tế theo quy tắc CORS.

Không phải mọi request đều có preflight. Một số request đơn giản có thể được gửi trực tiếp; trình duyệt vẫn kiểm tra response CORS trước khi cho JavaScript đọc kết quả.

## 3. CORS toàn cục trong Spring Data REST

Spring Data REST cho phép cấu hình CORS cho các repository resource thông qua giao diện **RepositoryRestConfigurer**. Phương thức **configureRepositoryRestConfiguration** nhận đối tượng **CorsRegistry**, từ đó đăng ký mapping và chính sách CORS.

Ví dụ cấu hình cho API repository:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class RepositoryCorsConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        cors.addMapping("/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods(
                "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"
            )
            .allowedHeaders(
                "Accept",
                "Content-Type",
                "Authorization",
                "If-Match",
                "If-None-Match"
            )
            .exposedHeaders(
                "Location",
                "ETag",
                "Link"
            )
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~

Cấu hình trên minh họa một frontend có origin cố định. Mapping **/*** áp dụng cho các đường dẫn repository do Spring Data REST quản lý. Nếu ứng dụng cần giới hạn phạm vi hơn, hãy dùng path pattern phù hợp với base path và repository resource thực tế.

Các phương thức trong CorsRegistry có vai trò riêng. Không nên coi chúng là những cách viết khác nhau của cùng một danh sách header.

## 4. Ý nghĩa của từng cấu hình CorsRegistry

| Phương thức | Vai trò | Ví dụ |
|---|---|---|
| **addMapping(path)** | Chọn các đường dẫn áp dụng CORS | **/*** |
| **allowedOrigins(...)** | Khai báo origin được phép | **https://app.example.com** |
| **allowedMethods(...)** | Khai báo HTTP method được phép | GET, POST, PATCH |
| **allowedHeaders(...)** | Khai báo request header client được gửi | Authorization, Content-Type |
| **exposedHeaders(...)** | Khai báo response header JavaScript được đọc | Location, ETag, Link |
| **allowCredentials(true)** | Cho phép request cross-origin dùng credentials theo chính sách trình duyệt | Cookie hoặc credential được hỗ trợ |
| **maxAge(seconds)** | Thời gian trình duyệt có thể cache kết quả preflight | 3600 |

### addMapping

**addMapping** nhận path pattern của các handler áp dụng CORS. Ví dụ **/*** phù hợp khi muốn áp dụng một chính sách cho toàn bộ repository endpoint được cấu hình trong Spring Data REST.

Nếu API có base path riêng như **/api**, cần kiểm tra cách base path được ánh xạ trong ứng dụng và chọn pattern khớp với handler path thực tế. Không thêm hoặc bỏ prefix theo suy đoán; kiểm tra request URL và cấu hình exporter.

### allowedOrigins

**allowedOrigins** liệt kê origin cụ thể được phép truy cập:

~~~java
.allowedOrigins(
    "https://app.example.com",
    "https://admin.example.com"
)
~~~

Origin phải khớp scheme, host và port. Ví dụ https://app.example.com và http://app.example.com là hai origin khác nhau. Một origin chạy ở port 3000 cũng khác origin trên port 443.

Chỉ khai báo các frontend thực sự cần truy cập API. Không đưa path như /dashboard vào origin vì path không thuộc thành phần origin.

### allowedMethods

**allowedMethods** quyết định method cross-origin nào được cho phép:

~~~java
.allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE")
~~~

Chọn đúng method mà API cung cấp. Nếu browser cần thực hiện preflight OPTIONS, framework xử lý OPTIONS cho CORS; có thể khai báo rõ OPTIONS trong danh sách khi phù hợp với cấu hình và cách triển khai của ứng dụng.

CORS cho phép method đi qua kiểm tra của trình duyệt. Server vẫn phải kiểm tra endpoint có thực sự hỗ trợ method đó và người gọi có quyền thực hiện hay không.

### allowedHeaders

**allowedHeaders** là request header mà frontend được phép gửi:

~~~java
.allowedHeaders(
    "Accept",
    "Content-Type",
    "Authorization",
    "If-Match"
)
~~~

Nếu frontend gửi Authorization hoặc một header tùy chỉnh nhưng header đó không được cho phép, preflight có thể thất bại.

Tên HTTP header không phân biệt chữ hoa/thường. Có thể khai báo rõ các header mà ứng dụng sử dụng để hợp đồng dễ đọc và giới hạn bề mặt request.

### exposedHeaders

**exposedHeaders** điều khiển response header mà JavaScript có thể đọc thông qua Fetch hoặc XMLHttpRequest:

~~~java
.exposedHeaders("Location", "ETag", "Link")
~~~

Trình duyệt chỉ expose một số response header mặc định. Nếu client cần đọc Location sau POST, ETag để gửi If-Match hoặc Link để khám phá hypermedia, hãy expose các header tương ứng.

Phân biệt:

- **allowedHeaders**: header frontend được phép gửi trong request.
- **exposedHeaders**: header frontend được phép đọc trong response.

Đưa ETag vào allowedHeaders không làm JavaScript đọc được ETag response. Ngược lại, expose Location không cho phép frontend tự gửi một request header Location.

### allowCredentials

Khi frontend gửi cookie hoặc credentials cross-origin, cấu hình cần cho phép credentials:

~~~java
.allowCredentials(true)
~~~

Phía frontend cũng cần yêu cầu gửi credentials, ví dụ Fetch dùng **credentials: "include"**. Cấu hình server và client phải phù hợp với cookie policy, SameSite, Secure và domain của cookie.

Khi cho phép credentials, không dùng wildcard origin **\*** trong Access-Control-Allow-Origin. Server cần trả origin cụ thể được chấp nhận. Dùng danh sách origin tin cậy; không phản chiếu tùy tiện giá trị Origin từ request.

### maxAge

**maxAge** cho trình duyệt biết thời gian có thể cache kết quả preflight:

~~~java
.maxAge(3600)
~~~

Giá trị tính bằng giây. Trong khoảng thời gian đó, browser có thể không cần gửi lại OPTIONS cho cùng tổ hợp origin, method và request headers theo quy tắc CORS.

maxAge chỉ cache kết quả preflight. Nó không phải TTL của dữ liệu API và không điều khiển HTTP response cache của GET.

## 5. Header request và response được tạo ra

Với cấu hình CORS phù hợp, server có thể trả các response header sau:

| Response header | Ý nghĩa |
|---|---|
| **Access-Control-Allow-Origin** | Origin được phép đọc response |
| **Access-Control-Allow-Methods** | Method được phép trong chính sách CORS |
| **Access-Control-Allow-Headers** | Request header được phép |
| **Access-Control-Expose-Headers** | Response header được expose cho JavaScript |
| **Access-Control-Allow-Credentials** | Cho biết response có cho phép credentials không |
| **Access-Control-Max-Age** | Thời gian cache kết quả preflight |
| **Vary: Origin** | Cho cache biết response có thể thay đổi theo Origin |

Spring Framework tạo các header này từ cấu hình CorsRegistry. Khi kiểm tra, hãy nhìn cả response OPTIONS và response của request thực tế.

Nếu server trả **Access-Control-Allow-Origin: https://app.example.com**, trình duyệt có thể cho JavaScript từ origin đó đọc response khi các điều kiện CORS khác cũng hợp lệ. Nếu origin không được chấp nhận, header có thể bị thiếu hoặc response không đáp ứng preflight.

## 6. Cấu hình theo phạm vi repository

Cấu hình trong RepositoryRestConfigurer thích hợp khi nhiều repository resource dùng chung một chính sách. Nếu một repository cần origin hoặc method riêng, có thể cân nhắc cấu hình ở phạm vi repository bằng annotation **@CrossOrigin** nếu phiên bản và mapping Spring Data REST của ứng dụng hỗ trợ.

Ví dụ:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.web.bind.annotation.CrossOrigin;

@CrossOrigin(origins = "https://app.example.com")
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Phạm vi hẹp hữu ích khi chỉ một repository cần được frontend cụ thể truy cập. Cấu hình toàn cục giúp tránh lặp lại cùng một chính sách trên nhiều repository.

Khi kết hợp global và repository-level configuration, hãy xác nhận quy tắc nào được áp dụng cho endpoint cụ thể. Tránh tạo nhiều CORS policy chồng lấn khiến response có header trùng hoặc giá trị không nhất quán.

## 7. CORS với Spring Security

Nếu ứng dụng dùng Spring Security, request OPTIONS preflight có thể bị security filter xử lý trước khi đến Spring MVC. Preflight thường không gửi cookie session như request thực tế, vì vậy nếu security yêu cầu authentication ngay lập tức, trình duyệt có thể nhận 401 hoặc 403 trước khi CORS được xử lý.

Hãy bật CORS integration trong SecurityFilterChain:

~~~java
import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.cors(withDefaults());

        // Giữ các quy tắc authentication/authorization hiện có.
        return http.build();
    }
}
~~~

Spring Security có thể dùng cấu hình CORS từ Spring MVC khi được tích hợp phù hợp, hoặc dùng một **CorsConfigurationSource** được khai báo riêng. Nếu ứng dụng đã có nguồn cấu hình CORS riêng cho security filter chain, hãy đồng bộ origin, method và header được phép với chính sách của repository exporter.

Không mở toàn bộ endpoint cho anonymous chỉ để làm preflight hoạt động. CORS cần được xử lý đúng thứ tự; authentication và authorization của request thực tế vẫn phải được giữ nguyên theo chính sách ứng dụng.

## 8. Ví dụ frontend gửi request có credentials

Nếu API dùng cookie session và cho phép frontend gửi credentials:

~~~javascript
const response = await fetch(
  "https://api.example.com/api/people",
  {
    method: "GET",
    credentials: "include",
    headers: {
      "Accept": "application/hal+json"
    }
  }
);

const etag = response.headers.get("ETag");
const location = response.headers.get("Location");
~~~

Server cần cho phép đúng origin và credentials. Nếu frontend cần đọc ETag hoặc Location, các header đó phải nằm trong exposedHeaders.

Nếu dùng bearer token thay vì cookie, frontend gửi Authorization:

~~~javascript
const response = await fetch(
  "https://api.example.com/api/people",
  {
    headers: {
      "Accept": "application/hal+json",
      "Authorization": "Bearer <access-token>"
    }
  }
);
~~~

Authorization thường khiến request cần preflight vì đây không phải request header CORS safelisted. Server cần cho phép header Authorization trong allowedHeaders. Việc CORS cho phép gửi header không xác thực token; authentication filter vẫn phải kiểm tra token.

## 9. Kiểm tra preflight bằng curl

curl không thực thi same-origin policy, nhưng có thể gửi request OPTIONS mô phỏng preflight để kiểm tra header server trả về.

~~~bash
curl -i -X OPTIONS \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type" \
  http://localhost:8080/api/people
~~~

Kiểm tra:

1. Response có status thành công cho preflight hay không.
2. Access-Control-Allow-Origin có đúng origin frontend không.
3. Access-Control-Allow-Methods có POST không.
4. Access-Control-Allow-Headers có Authorization và Content-Type không.
5. Access-Control-Max-Age có đúng thời gian mong muốn không.
6. Có Vary: Origin khi response phụ thuộc origin hay không.

Sau đó gửi request thực tế:

~~~bash
curl -i \
  -H "Origin: https://app.example.com" \
  -H "Accept: application/hal+json" \
  http://localhost:8080/api/people
~~~

Response thực tế cũng cần các CORS header phù hợp để browser cho JavaScript đọc nội dung. Chỉ kiểm tra OPTIONS là chưa đủ.

## 10. Kiểm tra trong browser DevTools

Mở tab Network và lọc theo request API:

- Tìm request **OPTIONS** trước POST/PUT/PATCH nếu browser thực hiện preflight.
- Xem Request Headers, đặc biệt Origin, Access-Control-Request-Method và Access-Control-Request-Headers.
- Xem Response Headers của preflight.
- Mở request thực tế và kiểm tra Access-Control-Allow-Origin.
- Nếu JavaScript đọc Location hoặc ETag ra null, kiểm tra Access-Control-Expose-Headers.
- Nếu request bị 401/403, xác định lỗi đến từ CORS handler hay authentication/authorization filter.

Thông báo CORS trên console thường chỉ cho biết browser không cho JavaScript đọc response. Hãy xem Network panel để xác định response thực tế, status code và header nào còn thiếu.

## 11. Những lỗi thường gặp

### Origin không khớp

Origin gồm scheme, host và port. http khác https; app.example.com khác api.example.com; port 3000 khác port 443. Khai báo đúng origin frontend đang chạy.

### Dùng wildcard với credentials

Access-Control-Allow-Origin không thể là wildcard khi response cho phép credentials. Dùng origin cụ thể và chỉ cho phép các frontend tin cậy.

### Đặt nhầm allowedHeaders và exposedHeaders

allowedHeaders dành cho request header client gửi. exposedHeaders dành cho response header JavaScript đọc. Nếu frontend không đọc được Location, hãy kiểm tra exposedHeaders.

### Preflight bị 401 hoặc 403

Spring Security có thể chặn OPTIONS trước khi CORS được xử lý. Bật CORS integration và bảo đảm cấu hình được áp dụng trước authentication cho preflight, trong khi request thực tế vẫn được bảo vệ.

### Chỉ cấu hình OPTIONS nhưng quên method thực tế

Preflight hỏi server về method như POST hoặc PATCH. allowedMethods phải cho phép method thực tế mà frontend sẽ gọi.

### curl thành công nhưng browser vẫn chặn

curl không áp dụng CORS. Hãy kiểm tra response header, origin thực tế, credentials, preflight và response của request thực tế trong DevTools.

### Cấu hình CORS nhưng quên expose Location hoặc ETag

Header có thể xuất hiện trong Network response nhưng JavaScript không đọc được. Thêm đúng response header vào exposedHeaders.

### Cho phép mọi origin không cần thiết

CORS policy quá rộng làm tăng bề mặt truy cập từ các website khác. Giới hạn origin, method và request header theo nhu cầu thật của frontend.

### Nghĩ CORS thay thế bảo mật API

Một chương trình ngoài browser vẫn có thể gọi endpoint. Server vẫn phải xác thực người dùng, phân quyền tài nguyên, chống CSRF khi dùng cookie và validate dữ liệu.

## 12. Ghi nhớ

- Origin được xác định bởi scheme, host và port.
- CORS cho phép browser đọc cross-origin response dựa trên policy của server.
- Preflight dùng OPTIONS để kiểm tra origin, method và request headers trước request thực tế.
- RepositoryRestConfigurer và CorsRegistry cấu hình CORS tập trung cho Spring Data REST repository resources.
- allowedOrigins, allowedMethods và allowedHeaders kiểm soát request; exposedHeaders kiểm soát response header JavaScript có thể đọc.
- allowCredentials cần chính sách origin cụ thể; không dùng wildcard origin cùng credentials.
- maxAge cache kết quả preflight, không phải TTL dữ liệu API.
- Khi dùng Spring Security, bảo đảm CORS được xử lý trước bước authentication chặn preflight.
- curl giúp kiểm tra HTTP header nhưng không mô phỏng browser enforcement; cần kiểm tra thêm trong DevTools.
- CORS không thay thế authentication, authorization, CSRF protection hoặc validation.

## Tài liệu tham khảo

- [Spring Data REST Reference — Configuring CORS](https://docs.spring.io/spring-data/rest/reference/cors.html)
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS)

# Giới hạn proxy được tin cậy để tránh sinh liên kết từ host giả mạo

## 1. Vấn đề và tác động đến Spring Data REST

Một ứng dụng Spring Data REST thường chạy sau reverse proxy, ingress controller hoặc load balancer. Client truy cập API bằng URL công khai như:

    https://api.example.com/api/orders

Trong khi đó, proxy có thể chuyển tiếp request nội bộ đến:

    http://10.20.0.15:8080/api/orders

Ứng dụng phía sau proxy nhìn thấy host, port và scheme của kết nối nội bộ. Để tạo URL trả về đúng cho client, proxy có thể gửi thông tin request ban đầu bằng các header:

- Forwarded: header chuẩn theo RFC 7239, có thể mang host, proto và thông tin các hop.
- X-Forwarded-Host: host công khai mà client đã gọi.
- X-Forwarded-Proto: scheme công khai, thường là https hoặc http.
- X-Forwarded-Port: port công khai.
- X-Forwarded-For: địa chỉ IP client theo chuỗi proxy.
- X-Forwarded-Prefix: prefix path công khai nếu proxy rewrite đường dẫn.

Spring Framework có thể dùng các header này để khôi phục request từ góc nhìn của client. Thông tin host và scheme sau đó có thể được dùng khi tạo redirect hoặc link trong JSON. Spring Data REST trả về tài liệu HAL với các liên kết self và related; nếu request bị dựng lại từ header giả mạo, các liên kết trả về có thể trỏ đến host do attacker chỉ định.

Ví dụ, client gửi:

    X-Forwarded-Host: attacker.example
    X-Forwarded-Proto: http

Nếu request đến thẳng ứng dụng hoặc proxy chuyển nguyên các header không đáng tin, một response HAL có thể chứa link mang host attacker.example. Điều này có thể làm hỏng link mà client theo sau, tạo redirect sai host hoặc khiến một hệ thống tiêu thụ link tin vào domain không mong muốn.

Nguyên tắc bảo mật quan trọng: **Forwarded và X-Forwarded-* chỉ đáng tin khi chúng được ghi bởi proxy nằm trong trust boundary.** Ứng dụng không thể tự biết một header được thêm bởi proxy hợp lệ hay do client bên ngoài tự gửi.

## 2. Ranh giới tin cậy phải được thiết lập ở proxy

Cấu hình Spring để đọc forwarded headers không xác thực danh tính proxy. Vì vậy, cần thiết lập ranh giới tin cậy trước khi bật xử lý header:

1. Proxy ở rìa hệ thống phải xóa các giá trị Forwarded và X-Forwarded-* do client gửi vào.
2. Sau khi xóa, proxy tự ghi lại những header cần thiết từ thông tin request đã được proxy xác thực.
3. Backend chỉ nhận kết nối từ proxy hoặc mạng nội bộ được cho phép. Không để port của ứng dụng có thể truy cập trực tiếp từ Internet.
4. Nếu có nhiều tầng proxy, xác định rõ hop nào được tin cậy, thứ tự các giá trị trong chuỗi header và nơi chịu trách nhiệm ghi đè header.
5. Kiểm tra Host header và cấu hình virtual host tại proxy. Chỉ nhận hostname công khai đã khai báo, không dùng một Host tùy ý từ request để dựng URL.

Cần xử lý cả hai họ header: Forwarded chuẩn và X-Forwarded-* không chuẩn. Spring Framework cảnh báo proxy ở rìa trust phải reset cả Forwarded lẫn X-Forwarded-* kể cả khi ứng dụng chỉ sử dụng một họ. Điều này tránh trường hợp một thành phần đọc Forwarded trong khi thành phần khác lại đọc X-Forwarded-Host.

Việc chỉ thêm server.forward-headers-strategy vào application.yml mà không cấu hình proxy xóa header không đáng tin là chưa đủ. Khi backend vẫn nhận request trực tiếp, client có thể bỏ qua proxy và gửi header giả mạo thẳng tới ứng dụng.

## 3. Chọn chiến lược xử lý forwarded headers trong Spring Boot

Spring Boot cung cấp property server.forward-headers-strategy với ba lựa chọn:

| Giá trị | Cách xử lý | Khi nên dùng |
|---|---|---|
| NONE | Không diễn giải forwarded headers | Ứng dụng không nằm sau proxy tin cậy hoặc không cần khôi phục URL công khai. |
| NATIVE | Dùng hỗ trợ của embedded web server | Container có hỗ trợ đúng các header proxy gửi và cấu hình trust của container đã được giới hạn. |
| FRAMEWORK | Dùng xử lý của Spring Framework | Cần ForwardedHeaderFilter trên Servlet stack hoặc ForwardedHeaderTransformer trên reactive stack. |

Với Spring Data REST chạy trên Spring MVC, FRAMEWORK đăng ký ForwardedHeaderFilter để điều chỉnh request dựa trên Forwarded hoặc X-Forwarded headers. Filter wrap request để các thành phần phía sau nhìn thấy host, port và scheme đã được khôi phục. Filter cũng loại bỏ forwarded headers khỏi request sau khi xử lý để chúng không tiếp tục tác động đến tầng dưới.

Nếu container hỗ trợ đúng bộ header của proxy, NATIVE có thể là lựa chọn phù hợp. Hỗ trợ cụ thể khác nhau theo server: Tomcat hỗ trợ X-Forwarded-*; Jetty và Reactor Netty hỗ trợ X-Forwarded-* và Forwarded theo tài liệu Spring Boot. Nếu cần xử lý không phụ thuộc vào khả năng native của container, cân nhắc FRAMEWORK.

Đừng dựa vào giá trị mặc định của nền tảng. Spring Boot có thể dùng NATIVE trên một số cloud platform được hỗ trợ và NONE trong các trường hợp khác. Hãy đặt giá trị tường minh theo topology thực tế.

### Cấu hình khi ứng dụng không cần proxy

Trong application.yml hoặc application-dev.yml, nếu client truy cập trực tiếp và không có proxy tin cậy, đặt:

~~~yaml
server:
  forward-headers-strategy: none
~~~

Khi đó, request header do client tự gửi như X-Forwarded-Host sẽ không được dùng để dựng request URL. Đây là cấu hình phù hợp cho local development hoặc môi trường test không mô phỏng reverse proxy.

### Cấu hình khi ứng dụng chạy sau proxy tin cậy

Nếu proxy đã xóa header do client gửi, tự ghi lại header chuẩn và backend chỉ nhận traffic từ proxy, có thể dùng Spring Framework:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Với lựa chọn này, Spring MVC dùng ForwardedHeaderFilter. Không đăng ký thêm một ForwardedHeaderFilter thứ hai nếu Spring Boot đã tự cấu hình filter qua property trên.

Nếu dùng Tomcat và TLS được kết thúc tại proxy, có thể cần thêm:

~~~yaml
server:
  tomcat:
    redirect-context-root: false
~~~

Thuộc tính này cho phép X-Forwarded-Proto được xử lý trước khi Tomcat thực hiện một số redirect ở context root. Chỉ áp dụng cấu hình này khi dùng Tomcat và topology TLS termination tương ứng.

### Dùng native support của Tomcat

Nếu chọn NATIVE, Tomcat có RemoteIpValve để diễn giải các header remote IP/protocol. Có thể giới hạn proxy nội bộ bằng server.tomcat.remoteip.internal-proxies. Đây là regular expression khớp địa chỉ IP proxy; hãy thay bằng dải địa chỉ thật của proxy trong hạ tầng:

~~~yaml
server:
  forward-headers-strategy: native
  tomcat:
    remoteip:
      internal-proxies: "10\\.20\\.0\\.\\d{1,3}"
~~~

Ví dụ trên chỉ khớp các địa chỉ 10.20.0.x. Không sao chép dải mẫu này nếu proxy thực tế dùng địa chỉ khác. Không đặt internal-proxies thành chuỗi rỗng trong production vì cấu hình đó có thể khiến mọi proxy được coi là đáng tin. Cấu hình native của Tomcat cũng có hành vi riêng theo loại header; kiểm tra tài liệu container nếu cần xử lý X-Forwarded-Host hoặc X-Forwarded-Prefix.

## 4. Ví dụ cấu hình reverse proxy

Ví dụ Nginx cho một hostname công khai cố định. Proxy chuyển request tới service Spring Data REST ở mạng nội bộ:

~~~nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    location / {
        proxy_pass http://spring-data-rest;

        proxy_set_header Host api.example.com;

        # Xóa header chuẩn do client gửi.
        proxy_set_header Forwarded "";

        # Ghi đè X-Forwarded-* bằng giá trị do proxy xác định.
        proxy_set_header X-Forwarded-Host api.example.com;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Ssl on;

        # Chỉ đặt X-Forwarded-Prefix khi proxy thực sự rewrite path.
        proxy_set_header X-Forwarded-Prefix "";
    }
}
~~~

Đây là ví dụ cho một host và một proxy ở rìa. Với nhiều hostname, dùng virtual host đã được kiểm tra hoặc một danh sách hostname cho phép; không chuyển nguyên Host/X-Forwarded-Host tùy ý từ client. Cấu hình default server của Nginx cũng cần từ chối hostname không được khai báo.

Trong ví dụ, X-Forwarded-For được đặt bằng $remote_addr, ghi lại địa chỉ peer mà Nginx nhìn thấy. Không dùng $proxy_add_x_forwarded_for một cách máy móc nếu header đầu vào có thể do client giả mạo. Khi có nhiều proxy tin cậy, thiết kế chuỗi địa chỉ và cách chọn client IP phải dựa trên danh sách hop được tin cậy của hạ tầng.

Nếu proxy công khai URL /api/orders và ứng dụng Spring Data REST cũng có base path /api, không cần thêm X-Forwarded-Prefix /api lần nữa. Chỉ dùng X-Forwarded-Prefix khi proxy thực sự rewrite hoặc thêm prefix khác với đường dẫn mà backend nhận được. Cấu hình prefix hai lần có thể làm link HAL thành /api/api/orders.

Sau khi cấu hình, giới hạn mạng để backend chỉ nhận traffic từ proxy. Có thể thực hiện bằng firewall, security group, Kubernetes NetworkPolicy hoặc cấu hình mạng nội bộ của nền tảng. Cấu hình header và giới hạn đường truy cập cần đi cùng nhau.

## 5. Spring Data REST và các liên kết HAL

Spring Data REST sử dụng thông tin request để tạo các link tự tham chiếu trong representation HAL. Ví dụ response collection có thể chứa:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders"
    }
  }
}
~~~

Nếu proxy terminate HTTPS nhưng ứng dụng chỉ nhìn thấy kết nối HTTP nội bộ, link có thể bị sinh thành http://... khi forwarded scheme không được xử lý. Tương tự, nếu host được khôi phục từ X-Forwarded-Host không đáng tin, self link có thể chứa hostname giả.

Khi kiểm tra response, hãy quan sát ít nhất:

- _links.self.href của collection endpoint.
- _links.self.href của một item endpoint.
- Header Location khi tạo resource và server trả về URI mới.
- Redirect Location nếu ứng dụng hoặc container phát sinh redirect.
- Scheme, host, port và prefix trong tất cả các URL công khai.

Không sửa từng link HAL thủ công trong repository hoặc controller để che vấn đề. Hãy sửa cách proxy ghi header và cách Spring dựng request URL, để mọi link được sinh ra nhất quán.

## 6. Kiểm thử trong ứng dụng

### Kiểm tra Spring MVC dùng forwarded headers

Với Spring Boot Servlet stack và Spring Data REST repository đã export tại /api/orders, có thể dùng MockMvc để xác nhận FRAMEWORK strategy dựng link từ header được cung cấp:

~~~java
@SpringBootTest(properties = {
    "server.forward-headers-strategy=framework"
})
@AutoConfigureMockMvc
class ForwardedLinkIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void usesForwardedHostAndSchemeForHalLinks() throws Exception {
        mockMvc.perform(get("/api/orders")
                .header("X-Forwarded-Host", "api.example.test")
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Port", "443")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href")
                .value(startsWith("https://api.example.test/api/orders")));
    }
}
~~~

Các import chính:

~~~java
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;
~~~

Test giả định ứng dụng có Spring MVC, Spring Data REST, repository được export ở path orders và có dependency test cho MockMvc. Điều chỉnh endpoint và cấu hình repository theo ứng dụng thực tế.

### Kiểm tra ứng dụng trực tiếp không tin header client

Trong profile local hoặc một test context riêng với:

~~~yaml
server:
  forward-headers-strategy: none
~~~

Gửi request có X-Forwarded-Host: attacker.example và xác nhận link trả về không chứa hostname này. Điều đó kiểm tra ứng dụng trực tiếp không diễn giải forwarded headers khi không có proxy được tin cậy.

Không dùng test MockMvc để kết luận rằng proxy thật đã xóa header client. MockMvc kiểm tra hành vi trong application context; nó không chạy Nginx, ingress controller, load balancer, firewall hay network policy.

### Kiểm tra xuyên qua proxy thật

Trong môi trường integration/staging, gửi request đến hostname công khai với các header giả mạo:

~~~bash
curl -i https://api.example.com/api/orders \
  -H 'Forwarded: host=attacker.example;proto=http' \
  -H 'X-Forwarded-Host: attacker.example' \
  -H 'X-Forwarded-Proto: http' \
  -H 'X-Forwarded-Port: 80'
~~~

Proxy phải loại bỏ hoặc ghi đè các giá trị client cung cấp. Response HAL vẫn phải dùng hostname và scheme chuẩn:

    https://api.example.com/api/orders

Kiểm tra thêm rằng request trực tiếp đến IP/port backend từ mạng không được phép bị từ chối. Nếu request giả mạo qua proxy vẫn làm thay đổi link, proxy chưa ghi đè đầy đủ header hoặc còn một proxy trung gian không nằm trong cấu hình trust.

## 7. Quy trình triển khai an toàn

1. Xác định proxy/load balancer nào thực sự kết thúc kết nối client và IP nguồn mà backend nhìn thấy.
2. Ghi lại bộ header mà proxy hỗ trợ: Forwarded hay X-Forwarded-*; xác định có rewrite path và cần X-Forwarded-Prefix hay không.
3. Cấu hình proxy xóa cả Forwarded và X-Forwarded-* từ request bên ngoài, sau đó ghi lại các giá trị canonical.
4. Chọn NONE, NATIVE hoặc FRAMEWORK trong Spring Boot theo loại embedded server và header cần xử lý.
5. Nếu dùng Tomcat native, cấu hình internal-proxies bằng regex chỉ khớp các proxy hợp lệ.
6. Đóng port backend khỏi Internet và chỉ cho proxy truy cập.
7. Kiểm tra HAL self links, Location và redirect qua proxy thật.
8. Gửi thử header giả mạo qua public endpoint và xác nhận link vẫn dùng host/scheme chính thức.
9. Kiểm tra request trực tiếp đến backend bị chặn.
10. Lặp lại kiểm tra sau mỗi lần đổi ingress, load balancer, service mesh hoặc network topology.

## 8. Troubleshooting

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| HAL self link trỏ tới host nội bộ như 10.x.x.x | Forwarded headers chưa được bật hoặc proxy không gửi host công khai | Kiểm tra X-Forwarded-Host/Forwarded host và chọn NATIVE hoặc FRAMEWORK phù hợp. |
| HAL link chứa attacker.example | Proxy chuyển nguyên header client hoặc backend nhận request trực tiếp | Xóa và ghi đè cả Forwarded lẫn X-Forwarded-* tại edge; giới hạn network tới backend. |
| Link dùng http thay vì https | Scheme công khai không được proxy gửi hoặc container không xử lý X-Forwarded-Proto | Đặt X-Forwarded-Proto=https tại proxy và kiểm tra strategy. Với Tomcat TLS termination, xem xét redirect-context-root=false. |
| Link có port nội bộ 8080 | X-Forwarded-Port không được gửi hoặc bị bỏ qua | Ghi đúng port công khai và xác nhận container/Framework xử lý header đó. |
| Link có /api/api | Base path của Spring Data REST và X-Forwarded-Prefix bị cộng trùng | Xác định path mà proxy gửi tới backend; chỉ đặt prefix khi proxy thực sự rewrite path. |
| NATIVE không xử lý header như mong muốn | Embedded server không hỗ trợ header hoặc hành vi cần thiết | Đọc tài liệu container; chuyển sang FRAMEWORK nếu phù hợp. |
| IP client không chính xác | Chuỗi X-Forwarded-For có giá trị do client chèn hoặc proxy chain chưa được mô hình hóa | Ghi đè ở edge; cấu hình danh sách hop tin cậy và chỉ đọc địa chỉ từ đúng proxy. |
| Chạy local tạo link sai sau khi bật FRAMEWORK | Local request có header forwarded giả hoặc profile dev cũng đang tin header | Dùng NONE cho dev/test trực tiếp; chỉ bật xử lý forwarded ở profile triển khai sau proxy tin cậy. |
| Chỉ một số request có link sai | Có nhiều proxy hoặc nhiều đường đi vào backend với quy tắc header khác nhau | Kiểm tra từng ingress/load balancer, thống nhất quy tắc strip và overwrite trên mọi đường vào. |

## 9. Checklist bảo mật

- [ ] Proxy ở trust boundary xóa header Forwarded do client gửi.
- [ ] Proxy ở trust boundary xóa hoặc ghi đè mọi header X-Forwarded-* do client gửi.
- [ ] Proxy tạo lại host, proto, port và prefix từ cấu hình/metadata đã xác thực.
- [ ] Hostname không hợp lệ bị từ chối ở reverse proxy.
- [ ] Backend chỉ nhận traffic từ proxy hoặc mạng nội bộ được cho phép.
- [ ] server.forward-headers-strategy được đặt tường minh cho từng môi trường.
- [ ] Nếu dùng Tomcat NATIVE, internal-proxies chỉ khớp các proxy hợp lệ.
- [ ] Không tin X-Forwarded-For để phân quyền nếu chưa xác định chuỗi proxy tin cậy.
- [ ] HAL self links và Location dùng đúng scheme, host, port và prefix công khai.
- [ ] Test gửi header giả mạo qua proxy thật vẫn nhận link canonical.
- [ ] Request trực tiếp tới backend từ mạng bên ngoài bị chặn.

## 10. Tài liệu tham khảo chính thức

- [Spring Boot — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/4.2/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server): lựa chọn server.forward-headers-strategy, hỗ trợ NATIVE/FRAMEWORK và cấu hình Tomcat proxy. Dùng tài liệu phiên bản Spring Boot tương ứng với dự án khi triển khai.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html): property server.forward-headers-strategy và các cấu hình embedded server.
- [Spring Framework — Filters / Forwarded Headers](https://docs.spring.io/spring/reference/web/webmvc/filters.html#filters-forwarded-headers): ForwardedHeaderFilter, các header được hỗ trợ, removeOnly và security considerations.
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239): định dạng header Forwarded tiêu chuẩn.
- [Spring Data REST Reference](https://docs.spring.io/spring-data/rest/reference/): repository resources và HAL representation được Spring Data REST cung cấp.

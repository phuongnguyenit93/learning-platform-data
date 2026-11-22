# Vai trò của Spring Web trong ứng dụng Java và các loại ứng dụng web

## 1. Spring Web giải quyết bài toán gì?

Một ứng dụng Java thông thường có thể chạy theo dòng lệnh, thực hiện tác vụ theo lịch hoặc xử lý dữ liệu mà không nhận yêu cầu HTTP. Khi muốn cung cấp website hoặc dịch vụ qua mạng, ứng dụng cần tiếp nhận HTTP request, xác định chức năng phải chạy, xử lý dữ liệu và gửi HTTP response cho trình duyệt, ứng dụng di động hoặc hệ thống khác.

**Spring Web** là nhóm thành phần của Spring Framework giúp xây dựng tầng giao tiếp web trên nền tảng Java. Thay vì tự đọc HTTP request và tự điều phối từng Servlet cho mọi URL, lập trình viên có thể khai báo điểm nhận request, tham số, dữ liệu đầu vào, kết quả và quy tắc xử lý lỗi bằng các thành phần Spring.

Ví dụ yêu cầu:

```http
GET /api/books/42 HTTP/1.1
Host: example.com
Accept: application/json
```

Ứng dụng có thể trả về:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"title":"Java cơ bản"}
```

Đây là ví dụ minh họa giao thức: Spring giúp ánh xạ `GET /api/books/42` tới mã xử lý, chuyển `42` thành tham số, rồi chuyển đối tượng kết quả thành JSON khi cấu hình thư viện chuyển đổi phù hợp.

Cần phân biệt ba tên thường gặp:

- **Spring Framework** là nền tảng có IoC/DI và nhiều module, trong đó có các module web.
- **Spring Web / Spring MVC / Spring WebFlux** là các thành phần phục vụ xử lý web của Spring Framework. `spring-web` cung cấp nhiều nền tảng HTTP chung; `spring-webmvc` triển khai mô hình MVC trên Servlet; `spring-webflux` triển khai stack web reactive.
- **Spring Boot** hỗ trợ cấu hình tự động, quản lý dependency và khởi động ứng dụng Spring nhanh hơn. Boot thường được dùng cùng Spring Web, nhưng Boot và Spring Web không đồng nghĩa.

## 2. Vai trò chính của Spring Web

### 2.1. Đưa logic Java ra giao diện HTTP

Spring định tuyến request theo đường dẫn và phương thức HTTP, ví dụ `GET /products` để đọc danh sách hoặc `POST /products` để tạo mới. Controller đóng vai trò tiếp nhận yêu cầu và chuyển việc xử lý nghiệp vụ cho service, thay vì ôm toàn bộ logic trong phương thức nhận HTTP.

Các annotation thường gặp trong Spring MVC gồm `@Controller`, `@RestController`, `@RequestMapping`, `@GetMapping`, `@PostMapping`, `@PathVariable`, `@RequestParam`, `@RequestBody`. Chúng khai báo giao ước nhận request và ràng buộc dữ liệu, không tự thay thế việc kiểm tra nghiệp vụ, xác thực hay quản lý giao dịch.

### 2.2. Chuyển đổi dữ liệu giữa HTTP và đối tượng Java

Ứng dụng có thể nhận dữ liệu từ path, query string, header, cookie, form hoặc request body; sau đó liên kết dữ liệu với tham số hoặc đối tượng Java. Với REST API, Spring thường dùng HTTP message converters/codecs để đọc và ghi JSON. Việc chuyển thành JSON thường cần thư viện serialization thích hợp, vốn được các starter tương ứng hỗ trợ cấu hình.

Ví dụ `GET /api/books?limit=10` chứa query parameter `limit`; trong khi `POST /api/books` có thể chứa JSON ở request body. Hai nơi chứa dữ liệu này khác nhau và cần được xử lý đúng cách.

### 2.3. Tổ chức lớp web và tích hợp hệ sinh thái

Tầng web có thể kết hợp với Spring Validation để kiểm tra dữ liệu, Spring Security để xác thực/phân quyền, tầng service để xử lý nghiệp vụ, và repository để làm việc với cơ sở dữ liệu. Spring cũng có cơ chế xử lý ngoại lệ, cấu hình CORS, nội dung phản hồi, upload file, điều hướng trang và các khả năng web khác.

Một cách phân chia trách nhiệm dễ bảo trì:

```text
Client (trình duyệt / mobile / dịch vụ khác)
                 |
              HTTP(S)
                 v
Web server / servlet container / runtime HTTP
                 |
    Spring Web: routing + binding + response
                 |
              Controller
                 |
               Service
                 |
       Repository / hệ thống ngoài
                 |
            Dữ liệu/kết quả
```

Sơ đồ là cách nhìn logic, không phải quy định mọi dự án đều phải có đủ lớp hoặc một lần gọi phải đi qua repository. Security filter, interceptor, exception handler và các thành phần hạ tầng cũng có thể tham gia luồng xử lý.

## 3. Một HTTP request đi qua ứng dụng Spring MVC như thế nào?

Với stack Servlet/Spring MVC, luồng phổ biến là:

1. Trình duyệt hoặc client gửi request đến server. Servlet container, chẳng hạn Tomcat, nhận kết nối và chuyển request đến ứng dụng.
2. Các Servlet filter phù hợp được áp dụng; đây có thể là nơi xử lý một phần vấn đề liên quan đến bảo mật hoặc thông tin request.
3. `DispatcherServlet` của Spring MVC đóng vai trò bộ điều phối trung tâm, tìm handler/controller phù hợp nhờ hệ thống handler mapping.
4. Spring liên kết tham số, thực thi các bước cần thiết như chuyển đổi kiểu và validation nếu đã khai báo, rồi gọi phương thức controller.
5. Controller gọi service, xử lý kết quả hoặc lỗi; Spring tạo response bằng cách ghi body (ví dụ JSON) hoặc giải quyết tên view để render HTML.
6. Container trả HTTP status, header và body về client. Nếu có lỗi, exception resolver hoặc cơ chế xử lý lỗi có thể tạo response tương ứng.

`DispatcherServlet` là khái niệm trọng tâm của Spring MVC. Trong **Spring WebFlux**, bộ điều phối trung tâm của stack reactive thường là `DispatcherHandler`, và cách xử lý I/O khác với mô hình Servlet truyền thống.

HTTP có các trạng thái giàu ý nghĩa: `200 OK` khi đọc thành công, `201 Created` khi tạo tài nguyên, `400 Bad Request` khi yêu cầu sai, `401 Unauthorized` khi chưa có thông tin xác thực hợp lệ, `403 Forbidden` khi không đủ quyền, `404 Not Found` khi tài nguyên không tồn tại, và `500 Internal Server Error` cho lỗi phía server. Mã trạng thái thực tế phải phản ánh tình huống; Spring không tự chọn đúng mọi mã cho mọi nghiệp vụ nếu không thiết kế xử lý phù hợp.

## 4. Các loại ứng dụng web thường gặp

Có thể phân loại theo **cách tạo giao diện**, **cách client giao tiếp**, hoặc **cách triển khai hệ thống**. Các nhóm dưới đây là những chiều phân loại khác nhau, vì thế một sản phẩm có thể thuộc nhiều nhóm đồng thời.

### 4.1. Website render HTML ở server (server-side rendering)

Server nhận request, lấy dữ liệu và render HTML trước khi trả về trình duyệt. Trong Spring MVC, `@Controller` có thể trả về tên view, kết hợp một template engine như Thymeleaf.

```text
Browser -- GET /catalog --> Spring MVC Controller
        <-- HTML đã render -- Template + dữ liệu
```

Phù hợp với website nội dung, trang quản trị, biểu mẫu và sản phẩm muốn render giao diện phía server. Ưu điểm là luồng render tập trung, trang có nội dung HTML ngay trong response; đổi lại mỗi bước điều hướng/submit có thể kéo theo một request và render lại toàn bộ hoặc một phần trang, tùy thiết kế.

### 4.2. Backend REST API trả dữ liệu cho client

Server chủ yếu trả JSON (hoặc một định dạng dữ liệu khác), không nhất thiết tạo HTML. Mobile app, frontend JavaScript, hệ thống đối tác hoặc một dịch vụ khác sẽ tiêu thụ API. Spring MVC thường dùng `@RestController` cho dạng này.

```text
Mobile / SPA / Service -- HTTP + JSON --> Spring API
Mobile / SPA / Service <-- status + JSON -- Spring API
```

Ví dụ hệ thống quản lý đơn hàng có endpoint đọc đơn, tạo đơn, thay đổi trạng thái. Điểm quan trọng là thiết kế tài nguyên, phương thức HTTP, mã trạng thái, xác thực, validation và hợp đồng dữ liệu rõ ràng. **REST** là phong cách thiết kế API; sử dụng `@RestController` không tự bảo đảm toàn bộ API tuân thủ các ràng buộc REST.

### 4.3. Ứng dụng một trang (SPA) có backend Spring

SPA (ví dụ frontend dùng React, Vue hoặc Angular) tải phần lớn giao diện JavaScript ở trình duyệt, sau đó gọi API để lấy/cập nhật dữ liệu. Spring Web có thể đảm nhiệm backend API; frontend có thể được phục vụ cùng origin hoặc triển khai riêng qua CDN/web server.

Với frontend và backend khác origin, cần hiểu cấu hình CORS. CORS là cơ chế trình duyệt kiểm soát việc script đọc phản hồi cross-origin, **không phải** cơ chế xác thực hoặc phân quyền. Authentication/authorization vẫn phải thực hiện tại backend.

### 4.4. Web app có tương tác thời gian thực

Khi client cần nhận cập nhật liên tục như thông báo, chat, giá thay đổi hoặc tiến độ tác vụ, ứng dụng có thể dùng:

- **WebSocket** cho kết nối hai chiều lâu dài khi cả client và server cần chủ động gửi thông điệp.
- **Server-Sent Events (SSE)** cho luồng sự kiện chủ yếu một chiều từ server đến trình duyệt qua HTTP.
- **Polling/long polling** khi client chủ động kiểm tra cập nhật định kỳ hoặc giữ request chờ dữ liệu.

Spring hỗ trợ xây dựng những kiểu giao tiếp này, nhưng lựa chọn giao thức cần dựa trên tính hai chiều, hạ tầng, số lượng kết nối, cơ chế reconnect và yêu cầu bảo mật. Không phải chức năng “thời gian thực” nào cũng cần WebSocket.

### 4.5. Ứng dụng monolith và hệ thống microservices

Đây là cách chia ranh giới triển khai, không phải cách biểu diễn giao diện:

- **Monolith**: một đơn vị triển khai có thể chứa UI server-side, API, service và truy cập dữ liệu. Spring Web xử lý điểm vào HTTP của ứng dụng đó.
- **Microservices**: nhiều dịch vụ triển khai độc lập, mỗi dịch vụ có thể có Spring Web API riêng và liên lạc qua HTTP hoặc messaging. Hệ thống cần quan tâm timeout, xác thực giữa dịch vụ, observability, lỗi mạng và nhất quán dữ liệu.
- **Modular monolith**: vẫn triển khai thành một ứng dụng, nhưng chia module nghiệp vụ rõ ràng để giảm phụ thuộc giữa các phần.

Dùng Spring Web **không bắt buộc** chọn microservices; một ứng dụng monolith có cấu trúc tốt thường là điểm khởi đầu hợp lý khi chưa có yêu cầu phân tách triển khai.

### 4.6. Website tĩnh

Website chỉ gồm HTML/CSS/JS được tạo sẵn và không cần xử lý nghiệp vụ Java ở server có thể được phục vụ trực tiếp từ CDN hoặc web server. Không nhất thiết cần Spring Web. Khi website tĩnh gọi backend API riêng, Spring Web có thể chỉ xuất hiện ở phía backend.

### Bảng đối chiếu nhanh

| Dạng ứng dụng | Phản hồi/giao tiếp chính | Spring thường đảm nhiệm | Ví dụ |
|---|---|---|---|
| Website server-side | HTML render từ server | MVC controller + view resolver/template | Trang quản trị |
| Backend API | HTTP status + JSON | REST controller, binding, serialization | API đơn hàng |
| SPA + backend | JavaScript UI gọi HTTP API | Backend REST, security, CORS khi cần | Dashboard React |
| Real-time | WebSocket, SSE hoặc polling | Endpoint và hạ tầng sự kiện | Chat, thông báo |
| Microservices | API giữa nhiều dịch vụ | HTTP endpoint ở từng service | Dịch vụ thanh toán |
| Website tĩnh | Tệp HTML/CSS/JS | Không bắt buộc sử dụng Spring | Landing page tĩnh |

Một hệ thống có thể vừa là “SPA + REST API” ở góc nhìn giao diện, vừa là “modular monolith” ở góc nhìn triển khai, và có thêm “SSE” cho thông báo. Vì vậy không nên coi các hàng trong bảng là những lựa chọn loại trừ nhau.

## 5. Spring MVC và Spring WebFlux: hai stack web chính

Spring cung cấp hai mô hình xử lý web nổi bật. Cả hai có thể cung cấp HTTP endpoint, controller và xử lý request/response; sự khác biệt đáng chú ý nằm ở mô hình thực thi và tương tác I/O.

| Tiêu chí | Spring MVC | Spring WebFlux |
|---|---|---|
| Nền tảng điển hình | Servlet API, servlet container | Reactive Streams, runtime non-blocking |
| Bộ điều phối | `DispatcherServlet` | `DispatcherHandler` |
| Phong cách phổ biến | Controller trả đối tượng/giá trị thông thường; hỗ trợ async khi cần | Controller hoặc functional endpoint, thường dùng `Mono`/`Flux` |
| I/O chặn luồng | Phù hợp với nhiều thư viện blocking truyền thống | Cần tránh blocking trên luồng xử lý sự kiện; tối ưu khi toàn bộ đường I/O hỗ trợ non-blocking |
| Use case thường thấy | CRUD, HTML server-side, REST với JPA/JDBC | Nhiều I/O đồng thời, streaming, tương tác với downstream reactive |
| Đánh đổi | Mô hình dễ tiếp cận và hệ sinh thái Servlet lâu đời | Cần hiểu reactive programming, backpressure, scheduler và boundary blocking |

**Không có quy tắc “WebFlux luôn nhanh hơn MVC”.** Kết quả phụ thuộc tải, thời gian đợi I/O, nguồn lực hệ thống và toàn bộ dependency. Một WebFlux controller gọi trực tiếp JDBC hoặc thư viện blocking trên event-loop vẫn có thể gây nghẽn. Ngược lại, MVC có hỗ trợ xử lý bất đồng bộ và có thể đáp ứng tốt khối lượng lớn ứng dụng thông thường.

Một số ứng dụng còn có thể sử dụng Spring MVC với virtual threads tùy JDK, servlet container và cấu hình. Virtual threads và WebFlux là hai cách tiếp cận concurrency khác nhau; không nên suy ra một ứng dụng dùng Java mới nhất thì tự động trở thành reactive.

**Gợi ý chọn stack:** Nếu hệ thống là website hoặc REST CRUD dùng JPA/JDBC và các thư viện blocking, Spring MVC thường dễ bắt đầu và vận hành. Nếu luồng xử lý chủ yếu non-blocking, cần streaming và có đội ngũ hiểu reactive, cân nhắc Spring WebFlux sau khi đánh giá nhu cầu thực tế.

## 6. Ví dụ Spring MVC REST endpoint nhỏ

Ví dụ này dành cho **dự án Spring Boot đã có dependency web MVC** và JDK phù hợp với phiên bản Spring Boot đang dùng. Đây là một lớp Java hoàn chỉnh *trong dự án Spring Boot*, không phải chương trình độc lập có thể chạy chỉ bằng `javac DemoApplication.java`: cần dependency Spring và tác vụ chạy của hệ thống build.

Tạo tệp `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@RestController
class GreetingController {
    @GetMapping("/api/hello")
    public Map<String, String> hello(
            @RequestParam(defaultValue = "bạn") String name) {
        return Map.of("message", "Xin chào, " + name);
    }
}
```

Chạy ứng dụng bằng tác vụ tương ứng với dự án, chẳng hạn `./gradlew bootRun` (trên Windows có thể dùng `gradlew.bat bootRun`) nếu dự án có Spring Boot Gradle plugin và cấu hình web phù hợp. Khi ứng dụng đang lắng nghe tại cổng mặc định 8080, gửi:

```bash
curl -s "http://localhost:8080/api/hello?name=Lan"
```

Response body dự kiến (khi có bộ chuyển JSON được cấu hình, như thiết lập web MVC phổ biến):

```json
{"message":"Xin chào, Lan"}
```

Giải thích từng phần:

1. `@SpringBootApplication` đánh dấu entry point và bật cơ chế cấu hình phù hợp của Spring Boot.
2. `@RestController` cho biết giá trị trả về của phương thức handler được ghi vào HTTP response body thay vì hiểu như tên view.
3. `@GetMapping("/api/hello")` đăng ký handler cho HTTP GET ở đường dẫn đó.
4. `@RequestParam` đọc tham số `name` từ query string; khi vắng mặt, giá trị mặc định là `bạn`.
5. `Map.of` tạo dữ liệu Java; cơ chế HTTP message conversion chuyển map thành JSON để trả cho client. Phần nhập/xuất HTTP do Spring và runtime web thực hiện.

Nếu client truy cập `/api/hello` không có `name`, phản hồi sẽ mang thông điệp `Xin chào, bạn`. Ví dụ nhỏ này chỉ trình diễn định tuyến và serialization; trong ứng dụng thật, controller thường gọi service, thực hiện validation, xử lý lỗi và bảo vệ endpoint theo yêu cầu.

### Khi muốn trả HTML thay vì JSON

Trong dự án Spring MVC đã cấu hình template engine và có template phù hợp, controller thường có dạng:

```java
@Controller
class HomeController {
    @GetMapping("/home")
    String home(Model model) {
        model.addAttribute("title", "Trang chủ");
        return "home";
    }
}
```

Đây là **đoạn minh họa**, chưa chạy độc lập vì đã lược bỏ các `import`, cấu hình template engine và tệp template `home`. Khác với `@RestController`, giá trị `"home"` của một `@Controller` thông thường ở đây được hiểu là tên view để view resolver xử lý, thay vì body JSON.

## 7. Chọn loại ứng dụng và công nghệ cho từng yêu cầu

Bắt đầu từ **người tiêu thụ kết quả** và **kiểu tương tác**:

1. Nếu người dùng cần một website HTML render tại server, cân nhắc Spring MVC với template engine.
2. Nếu client là ứng dụng di động, SPA hoặc hệ thống khác, thiết kế HTTP API rõ ràng; Spring MVC hoặc WebFlux đều có thể phục vụ API.
3. Nếu cần cập nhật do server đẩy đến client, đánh giá SSE/WebSocket theo chiều giao tiếp và đặc tính tải.
4. Nếu nghiệp vụ chủ yếu dùng JDBC/JPA hoặc thư viện blocking, ưu tiên sự nhất quán với mô hình thực thi blocking; chỉ chuyển sang reactive khi có lý do cụ thể.
5. Chọn monolith, modular monolith hay microservices theo nhu cầu triển khai, quy mô nhóm và ranh giới nghiệp vụ; lựa chọn đó độc lập tương đối với chuyện render HTML hay trả JSON.

Ví dụ một website đặt vé có thể bắt đầu bằng một ứng dụng Spring MVC render HTML và kết nối cơ sở dữ liệu qua JPA. Khi bổ sung ứng dụng di động, cùng hệ thống có thể cung cấp REST API. Khi cần trạng thái chỗ ngồi cập nhật liên tục, có thể thêm SSE hoặc WebSocket. Các khả năng được mở rộng theo yêu cầu, không cần đổi toàn bộ ứng dụng thành microservices chỉ vì xuất hiện nhiều loại client.

## 8. Những hiểu nhầm và lỗi thiết kế phổ biến

- **“Spring Web là web server.”** Spring Web là framework tầng ứng dụng; web server/Servlet container hoặc runtime HTTP đảm nhiệm việc nhận kết nối mạng. Spring Boot có thể khởi chạy embedded server theo dependency và cấu hình, nhưng chúng là những vai trò khác nhau.
- **“Cứ dùng `@RestController` là API đạt chuẩn REST.”** Annotation chỉ cung cấp cách xử lý và ghi response; thiết kế resource, semantics của HTTP, status và hợp đồng API vẫn cần chủ động xây dựng.
- **“Controller nên chứa mọi logic.”** Nhồi validation nghiệp vụ, SQL và gọi hệ thống ngoài trực tiếp vào controller làm ứng dụng khó kiểm thử và bảo trì. Nên giữ controller mỏng, tách trách nhiệm vào service và các lớp phù hợp.
- **“CORS bảo vệ API.”** CORS chủ yếu là ràng buộc truy cập của JavaScript trong trình duyệt; API vẫn cần authentication, authorization, kiểm tra dữ liệu và các biện pháp bảo mật thực sự.
- **“Reactive nghĩa là mọi hàm chạy song song hoặc luôn nhanh.”** Reactive mô tả cách kết hợp và xử lý luồng bất đồng bộ, non-blocking; hiệu quả thực tế còn phụ thuộc điểm chặn luồng và tài nguyên.
- **“Một SPA bắt buộc cần Spring phục vụ file frontend.”** Frontend có thể được host riêng; Spring Web có thể chỉ cung cấp backend.
- **“Mỗi service phải triển khai dưới dạng microservice.”** Ranh giới code và ranh giới triển khai không giống nhau. Có thể tổ chức module nghiệp vụ rõ ràng trong cùng một ứng dụng.

## 9. Tự kiểm tra mức hiểu

**Tình huống 1:** Một ứng dụng iOS cần lấy danh sách sản phẩm dạng JSON. Spring Web đóng vai trò gì?  
**Giải đáp:** Cung cấp HTTP endpoint, ánh xạ request, gọi nghiệp vụ, chuyển đối tượng thành JSON và trả HTTP response. Spring không tạo giao diện iOS.

**Tình huống 2:** Website dùng Thymeleaf render trang tại server có cần REST API cho mọi màn hình không?  
**Giải đáp:** Không. Controller có thể trả view HTML trực tiếp; REST API chỉ cần khi có giao tiếp dữ liệu riêng hoặc client khác.

**Tình huống 3:** Ứng dụng Spring MVC dùng JPA nhưng cần thông báo tiến độ theo thời gian thực. Có nhất thiết viết lại toàn bộ bằng WebFlux không?  
**Giải đáp:** Không. Có thể đánh giá SSE, WebSocket hoặc polling trên kiến trúc hiện tại; cần thiết kế tài nguyên, timeout, reconnect và xử lý đồng thời phù hợp.

**Điểm cần nhớ:** Spring Web là lớp kết nối giữa giao thức web và logic ứng dụng Java. Loại ứng dụng được xác định bởi cách client tiêu thụ HTML/dữ liệu/sự kiện, còn Spring MVC hay WebFlux là lựa chọn stack xử lý web. Thiết kế monolith/microservices là chiều kiến trúc triển khai khác và không bị quyết định bởi việc dùng Spring Web.

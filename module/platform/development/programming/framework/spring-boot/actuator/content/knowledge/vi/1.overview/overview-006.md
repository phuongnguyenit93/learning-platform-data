# Phân biệt endpoint quản trị với API nghiệp vụ

## 1. Hai nhu cầu khác nhau trong cùng một ứng dụng

Một ứng dụng quản lý đơn hàng cần phục vụ ít nhất hai nhóm nhu cầu:

- Khách hàng muốn xem đơn, tạo đơn hoặc yêu cầu hủy theo quy tắc của cửa hàng.
- Người vận hành muốn biết ứng dụng còn hoạt động không, phiên bản nào đang chạy, số liệu xử lý ra sao và có cần điều chỉnh cấu hình vận hành hay không.

Nhóm đầu thuộc **API nghiệp vụ**: giao diện thực hiện hoặc truy vấn chức năng của miền bài toán. Nhóm sau thuộc **giao diện quản trị/vận hành**: giúp quan sát, chẩn đoán và điều khiển ứng dụng đang chạy.

Trong Spring Boot, Actuator cung cấp các endpoint phục vụ vận hành. Ví dụ, `health` trả thông tin sức khỏe ứng dụng, còn `loggers` cho phép xem và điều chỉnh mức ghi log. Ứng dụng vẫn có thể có các công cụ vận hành tự xây dựng ngoài Actuator.

**Điểm phân biệt quan trọng là mục đích và hợp đồng sử dụng**, không phải chỉ là tiền tố URL, phương thức HTTP hay người dùng có chức danh “quản trị viên”.

Ví dụ:

~~~text
GET  /api/orders/DEMO-001        → xem một đơn hàng
POST /api/orders/DEMO-001/cancel → yêu cầu hủy đơn theo quy tắc nghiệp vụ

GET  /actuator/health            → xem tình trạng ứng dụng
GET  /actuator/metrics           → khám phá số liệu ứng dụng
~~~

Các đường dẫn trên minh họa cách phân loại. Chúng chỉ tồn tại khi ứng dụng triển khai hoặc cấu hình tương ứng.

## 2. So sánh theo trách nhiệm

| Tiêu chí | API nghiệp vụ | Endpoint quản trị/vận hành |
| --- | --- | --- |
| Câu hỏi chính | Hệ thống cung cấp chức năng gì cho người dùng hoặc hệ thống khác? | Ứng dụng đang chạy ra sao và cần được vận hành thế nào? |
| Đối tượng dữ liệu | Đơn hàng, sản phẩm, thanh toán, tài khoản | Sức khỏe, thông tin bản dựng, số liệu, cấu hình vận hành |
| Bên sử dụng điển hình | Giao diện người dùng, ứng dụng di động, đối tác, dịch vụ khác | Công cụ giám sát, bộ kiểm tra sức khỏe, người vận hành |
| Quy tắc quan trọng | Quyền sở hữu dữ liệu, trạng thái hợp lệ, tính nhất quán nghiệp vụ | Phạm vi thông tin được phép xem, quyền thao tác và khả năng truy cập của hạ tầng |
| Hậu quả khi gọi sai | Đọc nhầm dữ liệu, thay đổi sai đơn, thực hiện giao dịch không hợp lệ | Lộ thông tin kỹ thuật, thay đổi vận hành ngoài ý muốn, ảnh hưởng khả năng phục vụ |
| Hợp đồng cần kiểm thử | Dữ liệu đầu vào/đầu ra, quy tắc và kết quả nghiệp vụ | Nội dung chẩn đoán, phạm vi mở, quyền truy cập, khả năng hoạt động của công cụ vận hành |

### 2.1. “Quản trị viên dùng” chưa đủ để phân loại

Một nhân viên cửa hàng được phép hoàn tiền vẫn đang thực hiện **nghiệp vụ hoàn tiền**. API hoàn tiền cần kiểm tra đơn hàng, số tiền, quyền hạn và điều kiện hoàn tiền, dù URL có bắt đầu bằng `/admin`.

Ngược lại, một công cụ tự động gọi health không phải khách hàng mua hàng; nó đang dùng một giao diện vận hành, dù không có người đăng nhập trực tiếp.

Để phân loại, hãy hỏi: **kết quả của lời gọi mang ý nghĩa trong miền nghiệp vụ hay mô tả/điều chỉnh việc vận hành ứng dụng?**

### 2.2. Cùng trả JSON hoặc cùng có trường status không tạo ra cùng ý nghĩa

Hai phản hồi minh họa:

~~~json
{"orderId":"DEMO-001","status":"DRAFT"}
~~~

~~~json
{"status":"UP"}
~~~

`DRAFT` là trạng thái một đơn hàng theo mô hình nghiệp vụ. `UP` là trạng thái sức khỏe do cơ chế health tổng hợp. Cần đọc hợp đồng của từng endpoint để hiểu dữ liệu.

Một phản hồi health tốt không xác nhận đơn đã thanh toán hoặc quy tắc hủy đơn đã được thực thi đúng. Ngược lại, một lần đọc đơn thành công chưa chứng minh mọi phụ thuộc của ứng dụng đều hoạt động bình thường.

## 3. Actuator endpoint được tổ chức như thế nào?

### 3.1. Endpoint id và đường dẫn HTTP

Trong Actuator, endpoint có một định danh, chẳng hạn `health` hoặc `info`, và có thể cung cấp các thao tác đọc/ghi. Endpoint Actuator không đồng nghĩa với đúng một URL; một endpoint có thể có các thao tác hoặc đường dẫn con.

Với cấu hình HTTP mặc định, endpoint `health` thường được truy cập qua `/actuator/health`. Actuator còn hỗ trợ đưa các khả năng phù hợp ra những công nghệ khác như JMX. Annotation `@Endpoint` cùng các operation là cơ chế chuyên biệt cho khả năng quản trị này. Xem [Spring Boot 3.3 — Endpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/annotation/Endpoint.html).

API nghiệp vụ trong Spring MVC thường được viết bằng `@RestController` và các ánh xạ như `@GetMapping`, `@PostMapping`. Chỉ đặt một controller vào đường dẫn `/actuator/myOrders` không làm nó trở thành endpoint Actuator và không tự áp dụng cơ chế cấu hình exposure của Actuator cho controller đó.

Vì vậy, nên dành không gian đường dẫn rõ ràng cho hai nhóm để tránh xung đột và giúp cấu hình dễ hiểu. Đây là lựa chọn thiết kế; chính đường dẫn không tự tạo cơ chế bảo vệ.

### 3.2. Endpoint vận hành cũng có thể làm thay đổi ứng dụng

Không nên hiểu “quản trị” chỉ là đọc thông tin. Chẳng hạn endpoint `loggers` hỗ trợ:

~~~text
GET  /actuator/loggers/{logger.name}  → xem mức ghi log
POST /actuator/loggers/{logger.name}  → đặt hoặc xóa mức ghi log cấu hình
~~~

Thay đổi mức log có thể ảnh hưởng lượng dữ liệu ghi, chi phí và thông tin được phát ra. Vì thế, quyền xem số liệu không mặc nhiên đi kèm quyền thay đổi mức log. Xem [Spring Boot 3.3 — Loggers REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html).

Tương tự, không nên xem mọi thao tác đọc là vô hại. Thông tin về thành phần, cấu hình, luồng hay bộ nhớ có thể nhạy cảm. Hãy xác định dữ liệu và tác dụng của từng thao tác thay vì chỉ nhìn chữ `GET` hay `POST`.

### 3.3. Đọc health theo đúng phạm vi kiểm tra

Health mô tả sức khỏe theo những thành phần và kiểm tra đã được cấu hình. Trường `components` và `details` có thể được hiển thị hoặc ẩn theo cấu hình; không phải mọi người gọi đều cần xem toàn bộ chi tiết.

Một kiểm tra kết nối cơ sở dữ liệu thành công không thay thế việc kiểm thử một luồng đặt hàng hoàn chỉnh. Khi cần đánh giá trải nghiệm đặt hàng, phải xác minh riêng đường đi nghiệp vụ tương ứng. Xem [Spring Boot 3.3 — Health REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

## 4. Tách ba quyết định: bật, đưa ra ngoài và cho phép truy cập

Với một endpoint Actuator trên HTTP, cần phân biệt ba câu hỏi:

1. **Đã bật và đủ điều kiện tạo endpoint chưa?** Endpoint có được cấu hình sử dụng và có các thành phần nó cần không?
2. **Đã được đưa ra HTTP chưa?** Endpoint có nằm trong phạm vi exposure của giao diện HTTP không?
3. **Bên gọi có được truy cập không?** Quy tắc xác thực, phân quyền và mạng có cho phép yêu cầu này không?

Đây là ba góc nhìn cần kiểm tra, không phải ba tên gọi của cùng một thuộc tính.

### 4.1. Bật endpoint khác với mở endpoint qua HTTP

Trong Spring Boot 3.3.x, cấu hình `management.endpoint.<id>.enabled` điều khiển việc bật một endpoint. Cấu hình `management.endpoints.web.exposure.include` hoặc `exclude` chọn endpoint đưa ra HTTP; exclude được ưu tiên khi trùng nhau. Mặc định chỉ health được đưa ra HTTP.

Ví dụ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Cấu hình chọn `health` và `info` để đưa ra HTTP khi các endpoint tương ứng khả dụng. Nó không tạo API đặt hàng và cũng không tự cấp một vai trò bảo mật cho bên gọi. Xem [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Một biến thể dùng để làm rõ hai quyết định:

~~~yaml
management:
  endpoint:
    info:
      enabled: false
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Dù `info` được ghi trong include, nó vẫn bị tắt bởi cấu hình enabled. Include không làm sống lại endpoint đã tắt. Các thuộc tính tương ứng được liệt kê trong [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

### 4.2. Xác thực và phân quyền vẫn là trách nhiệm riêng

**Xác thực (authentication)** xác định bên gọi là ai. **Phân quyền (authorization)** xác định bên đó được phép xem hoặc thực hiện thao tác nào.

Nếu Spring Security có trên classpath, Spring Boot cung cấp cấu hình bảo mật mặc định. Khi ứng dụng tự định nghĩa một `SecurityFilterChain`, không được mặc định cho rằng các quy tắc bảo vệ Actuator do Boot cung cấp vẫn tiếp tục áp dụng nguyên vẹn: cấu hình tùy chỉnh cần bao phủ những URL cần bảo vệ. Xem [Spring Boot 3.3 — Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html).

Ví dụ chính sách **minh họa để thiết kế**, không phải mặc định Spring Boot:

| Bên gọi | Khả năng được cấp |
| --- | --- |
| Người mua hàng | Xem/thao tác các đơn thuộc phạm vi được phép |
| Bộ kiểm tra sức khỏe | Đọc kết quả health tối thiểu cần cho việc điều phối |
| Công cụ giám sát | Đọc các endpoint số liệu đã được duyệt |
| Nhân sự vận hành có quyền thay đổi | Thực hiện các thao tác vận hành cụ thể được cấp quyền |

Vai trò “người mua hàng” không được suy ra thành quyền quản trị ứng dụng; vai trò vận hành cũng không mặc nhiên cho phép đọc mọi đơn của khách hàng.

### 4.3. Khi cần tách các nhóm quy tắc bảo mật

Trong ứng dụng Servlet, `EndpointRequest` giúp tạo matcher theo các endpoint Actuator thực tế. `EndpointRequest.toAnyEndpoint()` bao gồm cả trang liên kết ở base path; `EndpointRequest.to("health")` có thể chọn riêng endpoint health. Cách này phù hợp hơn việc giả định mọi triển khai luôn dùng một chuỗi đường dẫn cố định. Xem [Spring Boot 3.3 — EndpointRequest API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html).

Có thể dùng nhiều `SecurityFilterChain` để tách chính sách quản trị và nghiệp vụ. Cần chú ý:

- Bộ lọc nào khớp yêu cầu được quyết định theo matcher và thứ tự ưu tiên.
- Một chain chỉ khớp Actuator không tự bảo vệ các URL nghiệp vụ còn lại.
- Cần một chain thích hợp bao phủ phần còn lại; không có chain nào khớp có thể để yêu cầu nằm ngoài bảo vệ của Spring Security.
- Quy tắc cho một thao tác đọc không đủ để kết luận thao tác ghi cũng được chấp nhận; còn phải xét cơ chế như CSRF theo mô hình xác thực.

Đây là định hướng thiết kế, không phải cấu hình hoàn chỉnh để sao chép vào mọi ứng dụng. Cơ chế nhiều chain được trình bày trong [Spring Security — Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html).

## 5. Cùng cổng hay tách cổng: thay đổi đường tiếp cận, giữ nguyên ý nghĩa

Theo cách triển khai thông dụng, API nghiệp vụ và HTTP endpoint Actuator có thể dùng cùng cổng:

~~~text
127.0.0.1:8080
├── /api/orders/demo   → dữ liệu đơn hàng minh họa
└── /actuator/health   → sức khỏe ứng dụng
~~~

Có thể đặt `management.server.port` để đưa các endpoint quản trị sang cổng khác. `management.endpoints.web.base-path` thay đổi tiền tố Actuator. Ví dụ:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      base-path: /manage
~~~

Khi không có cấu hình đường dẫn nền khác, health chuyển sang `http://localhost:8081/manage/health`. API nghiệp vụ vẫn ở cổng ứng dụng chính.

Tách cổng giúp triển khai tuyến mạng và chính sách truy cập riêng, nhưng **khác số cổng không có nghĩa là tự động riêng tư**. Cần xác định địa chỉ lắng nghe, các cổng được công bố, reverse proxy, tường lửa và quyền truy cập.

Không nên đổi base path chỉ để “giấu URL” rồi coi đó là xác thực. Cũng không cần tách thành hai ứng dụng hoặc hai tiến trình Java chỉ vì dùng hai cổng. Các tùy chọn port, address và base path được mô tả trong [Spring Boot 3.3 — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

## 6. Thực nghiệm: nhìn rõ hai nhóm endpoint

Thực nghiệm sau dành cho **một dự án thử nghiệm Spring Boot 3.3.x, Java 17 trở lên**, đã có Gradle wrapper, quản lý phiên bản dependency và tác vụ bootRun. Nó không phải thay đổi cần áp dụng cho mọi module.

Dự án thử nghiệm chỉ dùng Web và Actuator, không có Spring Security, không có cơ sở dữ liệu và không đổi context path. Chỉ lắng nghe loopback để quan sát hành vi cục bộ.

### 6.1. Dependency và mã ứng dụng

Phần dependency ghép vào `build.gradle` của dự án:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Tạo `src/main/java/example/boundary/EndpointBoundaryDemoApplication.java`:

~~~java
package example.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class EndpointBoundaryDemoApplication {
    @GetMapping("/api/orders/demo")
    public OrderView demoOrder() {
        return new OrderView("DEMO-001", "DRAFT");
    }

    public record OrderView(String orderId, String status) {
    }

    public static void main(String[] args) {
        SpringApplication.run(EndpointBoundaryDemoApplication.class, args);
    }
}
~~~

Đây là một tệp Java hoàn chỉnh trong dự án đã nêu. Đơn hàng được tạo cố định để minh họa, không đọc dữ liệu khách hàng và không ghi cơ sở dữ liệu. Endpoint GET chỉ trả dữ liệu mẫu.

Actuator tạo health theo cơ chế của nó; mã trên chỉ khai báo API nghiệp vụ. Không có phương thức controller tự viết nào cho `/actuator/health`.

### 6.2. Lần chạy A: cùng cổng

Đặt `src/main/resources/application.yml`:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Chạy trong thư mục dự án:

~~~powershell
.\gradlew.bat bootRun
~~~

Ở cửa sổ khác, đọc dữ liệu mẫu:

~~~powershell
curl.exe --silent --show-error http://127.0.0.1:8080/api/orders/demo
~~~

Các trường và giá trị JSON mong đợi:

~~~json
{"orderId":"DEMO-001","status":"DRAFT"}
~~~

Thứ tự trường JSON không mang ý nghĩa nghiệp vụ. Đây là nội dung HTTP response body, không phải một dòng được Java in ra stdout.

Tiếp tục đọc health:

~~~powershell
curl.exe --silent --show-error http://127.0.0.1:8080/actuator/health
~~~

Nếu các kiểm tra sức khỏe hiện có đều tốt và không cấu hình hiển thị chi tiết, phản hồi thông thường là:

~~~json
{"status":"UP"}
~~~

Hai yêu cầu cùng đến một tiến trình và một cổng nhưng phục vụ hai hợp đồng khác nhau.

Có thể gọi `/actuator/info` vì đã đưa endpoint đó ra HTTP. Nội dung do các `InfoContributor` cung cấp; nếu dự án không có thông tin để đóng góp, kết quả có thể chỉ là `{}`. Exposure không tự sinh thông tin bản dựng. Xem [Spring Boot 3.3 — Info REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/info.html).

### 6.3. Lần chạy B: cổng quản trị riêng

Dừng ứng dụng. Thay toàn bộ YAML của lần A bằng cấu hình dưới đây rồi khởi động lại:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  server:
    address: 127.0.0.1
    port: 8081
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Lần này, gọi đúng địa chỉ theo từng nhóm:

~~~powershell
curl.exe --silent --show-error http://127.0.0.1:8080/api/orders/demo
curl.exe --silent --show-error http://127.0.0.1:8081/actuator/health
~~~

Trong cấu hình thử nghiệm chuẩn ở trên, ma trận kết quả mong đợi là:

| Cổng | Đường dẫn | Kết quả |
| --- | --- | --- |
| 8080 | `/api/orders/demo` | 200, dữ liệu đơn mẫu |
| 8081 | `/actuator/health` | 200 khi health đang UP |
| 8080 | `/actuator/health` | 404, endpoint đã chuyển sang cổng quản trị |
| 8081 | `/api/orders/demo` | 404, không có API nghiệp vụ đó trên máy chủ quản trị |
| 8081 | `/actuator/env` | 404, không được đưa ra HTTP trong cấu hình này |

Để chỉ xem mã trạng thái của một trường hợp:

~~~powershell
curl.exe --silent --output NUL --write-out "%{http_code}" http://127.0.0.1:8080/actuator/health
~~~

Đầu ra dự kiến:

~~~text
404
~~~

Dùng `curl.exe` để gọi chương trình curl trên Windows, tránh khác biệt alias của PowerShell. Các kết quả 404 trên chỉ áp dụng khi không có controller trùng đường dẫn, proxy viết lại URL hoặc cấu hình bổ sung khác.

Việc riêng một cổng health trả kết quả tốt cũng không chứng minh đường truy cập nghiệp vụ qua cổng chính và proxy đã hoạt động. Cần kiểm tra cả tuyến thực tế mà người dùng sử dụng.

### 6.4. Quan sát quyền truy cập một cách có điều kiện

Ví dụ chưa đưa Spring Security vào để giúp nhìn riêng sự khác nhau về ánh xạ. Trong dự án thực tế có bảo mật, một yêu cầu chưa được phép có thể bị xử lý trước khi tới endpoint.

Không nên dùng một quy tắc tuyệt đối như “404 luôn là chưa expose” hoặc “403 luôn là sai vai trò”. Kết quả còn phụ thuộc chain, CSRF, bộ xử lý lỗi và proxy. Hãy đối chiếu cấu hình, thông tin xác thực và log thay vì suy ra nguyên nhân duy nhất từ một mã HTTP.

Nếu dùng nhiều cổng trong container hoặc trên máy chủ, hãy kiểm tra cả cấu hình công bố cổng và địa chỉ mà công cụ giám sát có thể tiếp cận. Loopback của một tiến trình trong container không tự trở thành loopback mà mọi container khác có thể gọi.

## 7. Phân loại các trường hợp dễ nhầm

### 7.1. Hủy đơn, xóa cache và thay đổi mức log

- **Hủy đơn:** thay đổi trạng thái một đối tượng nghiệp vụ; cần quy tắc hủy, quyền sở hữu và bảo đảm nhất quán.
- **Xóa một cache vận hành:** thay đổi cách ứng dụng phục vụ và có thể gây tăng tải; cần chính sách vận hành và đánh giá tác động.
- **Thay đổi mức log:** điều chỉnh hành vi chẩn đoán; không phải giao dịch mua hàng, nhưng vẫn là thao tác có tác dụng phụ.

Không nên chuyển thao tác hủy đơn thành một endpoint Actuator để tránh xây dựng xác thực hoặc kiểm tra nghiệp vụ. Cũng không nên công khai thao tác vận hành chỉ vì nó không sửa trực tiếp bảng đơn hàng.

Nếu “xóa cache” thực chất là một phần quy trình làm mới dữ liệu nghiệp vụ đã được định nghĩa cho người dùng, cần phân tích hợp đồng cụ thể. Tên hành động riêng lẻ chưa quyết định toàn bộ thiết kế.

### 7.2. Bên gọi đều là dịch vụ nội bộ

Một dịch vụ thanh toán gọi API ghi nhận kết quả thanh toán đang tương tác với nghiệp vụ. Prometheus đọc metrics đang tương tác với khả năng vận hành. Cả hai có thể là máy gọi máy và đều cần danh tính/quyền hạn thích hợp.

Từ “nội bộ” mô tả phạm vi triển khai; nó không thay thế việc định nghĩa ai được làm gì.

### 7.3. Tự xây công cụ vận hành

Ứng dụng có thể cần khả năng vận hành riêng. Nếu dùng Actuator, hãy thiết kế một endpoint có dữ liệu và operation phù hợp với cơ chế của Actuator, rồi cấu hình exposure và phân quyền tương ứng.

Nếu dùng controller HTTP thông thường cho một công cụ vận hành, nó vẫn phải được bảo vệ theo cấu hình controller/security của ứng dụng. Đừng giả định `management.endpoints.web.exposure.include` sẽ quản lý một controller chỉ vì URL của nó có chữ “manage”.

Dữ liệu quản trị nên mô tả điều cần quan sát hoặc điều khiển, tránh trả lại mọi trường của các đối tượng nghiệp vụ hay cấu hình nội bộ chỉ vì tiện triển khai.

## 8. Lỗi phổ biến và cách đối chiếu

| Hiểu nhầm | Cách kiểm tra |
| --- | --- |
| Mọi URL bắt đầu bằng /admin đều là Actuator | Xác định nó được tạo bởi controller hay cơ chế endpoint Actuator, rồi đọc mục đích |
| Thêm Actuator làm xuất hiện API tạo đơn | Kiểm tra mã nghiệp vụ; Actuator không tự biết quy tắc đơn hàng |
| Include một endpoint nghĩa là mọi người có quyền gọi | Kiểm tra riêng exposure, security và đường mạng |
| Cổng 8081 tự là cổng riêng tư | Xem địa chỉ lắng nghe, tuyến mạng, proxy và quyền truy cập |
| Health UP nghĩa là mọi đơn hàng đều xử lý đúng | Xác định health đang kiểm tra những gì; kiểm thử luồng nghiệp vụ riêng |
| Chỉ cần bảo vệ các request POST | Đánh giá cả dữ liệu bị đọc và các operation có tác dụng phụ |
| Tạo một chain Actuator là đủ bảo vệ ứng dụng | Kiểm tra chain bao phủ API nghiệp vụ và những đường dẫn còn lại |
| API nội bộ có thể bỏ qua quyền trên từng đơn | Kiểm tra danh tính bên gọi và quyền ở phạm vi dữ liệu cụ thể |

### Tự thực hành

1. Phân loại: đọc giỏ hàng, đọc health, thay đổi mức log, nhân viên hoàn tiền, hệ thống đọc metrics. Giải thích bằng mục đích thay vì tiền tố.
2. Một endpoint đã bật nhưng chưa nằm trong HTTP exposure. Việc cấp quyền cho một tài khoản có tự làm xuất hiện URL đó không?
3. Với cấu hình tách cổng trong ví dụ, dự đoán bốn cặp cổng/đường dẫn trước khi chạy curl.
4. Đổi base path quản trị thành `/manage`. Chỉ ra URL health mới và giải thích vì sao API đơn hàng không cần đổi theo.
5. Người dùng gọi API đơn hàng thành công nhưng health báo một phụ thuộc DOWN. Nêu thông tin cần bổ sung trước khi kết luận ứng dụng “tốt” hay “hỏng”.

**Gợi ý đối chiếu:** giỏ hàng và hoàn tiền thuộc nghiệp vụ; health, metrics và mức log thuộc vận hành. Quyền truy cập không thay cho exposure. Cần xem cấu hình cổng/base path thực tế. Health và kết quả một lời gọi nghiệp vụ cung cấp bằng chứng ở những phạm vi khác nhau.

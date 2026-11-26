# Cung cấp tài nguyên tĩnh và đường dẫn theo context

Ứng dụng Spring Web Flow thường hiển thị nhiều view trong một hành trình web: nhập dữ liệu, rà soát, xác nhận và hoàn tất. Các view này cần CSS, JavaScript, hình ảnh, font chữ và đôi khi các tệp tải xuống công khai. Những tài nguyên không cần xử lý theo từng request nghiệp vụ được gọi là **tài nguyên tĩnh**. Spring MVC có thể ánh xạ URL đến các thư mục chứa tài nguyên để trình duyệt tải chúng trực tiếp.

Một vấn đề thường gặp là ứng dụng được triển khai dưới context path khác nhau giữa môi trường phát triển, kiểm thử và production. Ví dụ, ứng dụng có thể chạy tại **/** ở máy cá nhân nhưng tại **/booking-portal** trên máy chủ. Nếu view viết cứng URL bắt đầu bằng **/resources/...**, trình duyệt sẽ yêu cầu tài nguyên từ gốc domain và bỏ qua context path. Kết quả là trang flow có thể hiển thị nhưng mất CSS, JavaScript hoặc hình ảnh.

Để tích hợp ổn định, cần cấu hình nơi Spring MVC tìm tài nguyên, chọn URL mapping không xung đột với flow, và tạo URL trong view theo context của ứng dụng. Cũng cần hiểu thêm servlet mapping vì context path và servlet path là hai thành phần khác nhau của URL.

## 1. Tài nguyên tĩnh và cấu trúc URL

Tài nguyên tĩnh thường gồm:

- CSS để định dạng view.
- JavaScript cho tương tác phía trình duyệt.
- Hình ảnh, biểu tượng và font chữ.
- Tệp tải xuống công khai không cần xử lý nghiệp vụ theo từng request.

Giả sử ứng dụng có cấu trúc:

~~~text
src/main/webapp/
└── resources/
    ├── css/
    │   └── booking.css
    ├── js/
    │   └── booking.js
    └── images/
        └── logo.svg
~~~

Và view JSP nằm trong:

~~~text
src/main/webapp/WEB-INF/views/booking/
├── enterDetails.jsp
└── review.jsp
~~~

Nếu Spring MVC ánh xạ URL **/resources/*** tới thư mục **/resources/**, thì URL **/resources/css/booking.css** sẽ được phân giải thành tệp **resources/css/booking.css** trong web application.

Một URL đầy đủ có thể có các thành phần:

~~~text
https://example.com/booking-portal/resources/css/booking.css
                     |               |
                     |               +-- path được MVC mapping xử lý
                     +-- context path
~~~

Trong ví dụ này:

- **/booking-portal** là context path, tức đường dẫn gốc của web application trong servlet container.
- **/resources/css/booking.css** là đường dẫn sau context path được servlet và Spring MVC xử lý theo mapping.

Nếu **DispatcherServlet** được ánh xạ vào một prefix như **/mvc/***, URL còn có phần servlet mapping:

~~~text
https://example.com/booking-portal/mvc/resources/css/booking.css
                     |               |   |
                     |               |   +-- handler path
                     |               +-- servlet mapping path
                     +-- context path
~~~

Vì vậy, không nên nhầm context path với servlet mapping path. Các ví dụ JSP ở phần sau giả định **DispatcherServlet** được ánh xạ ở root **/**. Nếu dự án dùng prefix riêng, hãy thêm prefix đó theo cấu trúc URL mà servlet container và ứng dụng đang sử dụng.

## 2. Cấu hình resource handler bằng XML

Spring MVC cung cấp namespace **mvc** để ánh xạ URL tới tài nguyên tĩnh. Trong application context có bật Spring MVC namespace, khai báo:

~~~xml
<mvc:resources mapping="/resources/**"
               location="/resources/"
               cache-period="3600"/>
~~~

Ý nghĩa:

- **mapping="/resources/**"** chỉ ra URL pattern mà resource handler nhận.
- **location="/resources/"** chỉ ra thư mục tài nguyên trong web application.
- **cache-period="3600"** cho phép trình duyệt cache tài nguyên trong 3.600 giây. Giá trị này là ví dụ; thời hạn thực tế nên dựa trên chiến lược phát hành tài nguyên.

Nếu tài nguyên được đóng gói trong classpath, có thể khai báo thêm location:

~~~xml
<mvc:resources mapping="/assets/**"
               location="classpath:/static/,classpath:/public/"/>
~~~

Khi đó, URL **/assets/css/site.css** được tìm trong các vị trí classpath đã khai báo theo quy tắc của resource handler. Hãy kiểm tra cấu trúc thư mục trong artifact đã đóng gói để bảo đảm tài nguyên thực sự có mặt ở vị trí tương ứng.

**<mvc:resources>** đăng ký resource handler trong Spring MVC. Nó không tạo controller cho từng tệp và không đưa tài nguyên vào flow scope. Flow vẫn đảm nhiệm state và transition; resource handler xử lý các request lấy nội dung tĩnh.

## 3. Cấu hình resource handler bằng Java

Với ứng dụng dùng Java configuration, có thể đăng ký tài nguyên bằng **WebMvcConfigurer**:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebMvcConfiguration implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/resources/**")
                .addResourceLocations("/resources/", "classpath:/static/")
                .setCachePeriod(3600);
    }
}
~~~

Đoạn cấu hình đăng ký cùng URL mapping và các vị trí tìm tệp như ví dụ XML. Nếu dự án đã có lớp **WebMvcConfigurer**, hãy thêm cấu hình vào lớp phù hợp hoặc tổ chức nhiều cấu hình theo cách Spring context của dự án quản lý; tránh tạo các mapping trùng nhau cho cùng một URL pattern.

Trong một số phiên bản Spring mới, có thể cấu hình cache bằng **CacheControl** thay cho thời hạn tính bằng giây. Hãy chọn API phù hợp với phiên bản Spring Framework mà dự án đang dùng. Dù dùng XML hay Java, nguyên tắc vẫn là mapping phải rõ ràng, location phải đúng và chính sách cache phải phù hợp với cách phát hành file.

## 4. Chọn vị trí lưu tài nguyên

Với ứng dụng web đóng gói thành WAR, các thư mục thường gặp gồm:

| Vị trí | Ví dụ location | Khi phù hợp |
|---|---|---|
| Web application root | **/resources/** | Tài nguyên nằm trong **src/main/webapp/resources** và được đóng gói vào WAR. |
| Classpath | **classpath:/static/** | Tài nguyên nằm trong thư mục classpath như **src/main/resources/static**. |
| Classpath dùng chung | **classpath:/public/** hoặc thư mục riêng của ứng dụng | Tài nguyên được cung cấp bởi module hoặc thư viện dùng chung. |

Chọn một cấu trúc nhất quán giúp người phát triển dễ tìm file và tránh sao chép tài nguyên giữa nhiều vị trí. Với dự án WAR truyền thống, **src/main/webapp/resources** là lựa chọn dễ hiểu. Với tài nguyên được đóng gói trong JAR hoặc module dùng chung, classpath location phù hợp hơn.

Không đặt view JSP cần bảo vệ trong thư mục public của tài nguyên tĩnh. View thường nằm dưới **WEB-INF** để trình duyệt không thể yêu cầu trực tiếp qua URL; Spring MVC hoặc Spring Web Flow chọn view và render chúng ở phía máy chủ.

## 5. Tạo URL đúng context path trong JSP

Không nên viết cứng:

~~~jsp
<link rel="stylesheet" href="/resources/css/booking.css">
<script src="/resources/js/booking.js"></script>
<img src="/resources/images/logo.svg" alt="Logo">
~~~

Dấu **/** ở đầu URL khiến trình duyệt bắt đầu từ root của domain. Khi ứng dụng nằm tại **/booking-portal**, trình duyệt vẫn yêu cầu **/resources/...** thay vì **/booking-portal/resources/...**.

Với JSP, JSTL **c:url** tạo URL có gắn context path:

~~~jsp
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core" %>

<link rel="stylesheet"
      href="<c:url value='/resources/css/booking.css'/>">

<script defer
        src="<c:url value='/resources/js/booking.js'/>"></script>

<img src="<c:url value='/resources/images/logo.svg'/>"
     alt="Logo">
~~~

Nếu context path là **/booking-portal**, **c:url** tạo đường dẫn tương ứng với context đó. Nếu ứng dụng được triển khai tại root context, phần context path có thể rỗng và URL vẫn hợp lệ.

Với Spring tag library, cũng có thể dùng **spring:url** trực tiếp:

~~~jsp
<%@ taglib prefix="spring" uri="http://www.springframework.org/tags" %>

<link rel="stylesheet"
      href="<spring:url value='/resources/css/booking.css'/>">
~~~

Các thẻ này giúp view thích ứng khi context path thay đổi. Nếu ứng dụng dùng servlet mapping prefix thay vì mapping root, cần bảo đảm URL sinh ra còn bao gồm prefix theo cấu trúc triển khai của servlet.

## 6. Tạo URL đúng context path trong Thymeleaf

Nếu view dùng Thymeleaf, cú pháp URL expression **@{...}** tự động tính context path:

~~~html
<link rel="stylesheet" th:href="@{/resources/css/booking.css}">
<script defer th:src="@{/resources/js/booking.js}"></script>
<img th:src="@{/resources/images/logo.svg}" alt="Logo">
~~~

Khi ứng dụng chạy tại context **/booking-portal**, Thymeleaf tạo URL tương ứng dưới context đó. Cách này cũng áp dụng cho liên kết tới endpoint Spring MVC:

~~~html
<a th:href="@{/booking/help}">Hướng dẫn đặt chỗ</a>
~~~

Đối với JSP, dùng **c:url** hoặc **spring:url**; đối với Thymeleaf, dùng **@{...}**. Tránh ghép chuỗi context path thủ công ở nhiều nơi vì dễ tạo dấu **/** thừa hoặc thiếu và khiến code phụ thuộc môi trường.

## 7. Đường dẫn tương đối trong view-state

View-state của Spring Web Flow thường được hiển thị tại một URL chứa flow id hoặc thông tin tiếp tục flow. Nếu view viết đường dẫn tương đối như:

~~~html
<link rel="stylesheet" href="resources/css/booking.css">
~~~

trình duyệt sẽ giải quyết URL dựa trên URL hiện tại của trang. Khi trang nằm dưới một đường dẫn lồng sâu hoặc URL có cấu trúc flow execution, đường dẫn có thể trỏ tới vị trí không mong muốn.

Hãy dùng URL bắt đầu từ context-aware root của ứng dụng thông qua tag hoặc template expression:

~~~jsp
<link rel="stylesheet"
      href="<c:url value='/resources/css/booking.css'/>">
~~~

Đối với liên kết nội bộ trong flow, cần phân biệt:

- URL tài nguyên tĩnh như CSS, JS và ảnh được resource handler xử lý.
- URL flow như **/booking** được **FlowHandlerMapping** nhận diện và **FlowHandlerAdapter** chuyển tới **FlowExecutor**.
- URL controller như **/booking/help** được handler mapping của Spring MVC ánh xạ đến controller tương ứng.

Không đặt tài nguyên tĩnh dưới một pattern URL dành riêng cho flow nếu điều đó khiến request tải CSS hoặc ảnh bị flow handler nhận nhầm. Nên dùng prefix riêng, ví dụ **/resources/** cho tài nguyên và **/booking/** cho flow.

## 8. Phối hợp resource handler với Spring Web Flow

Một ứng dụng Spring MVC tích hợp Spring Web Flow thường có nhiều **HandlerMapping**: mapping cho flow, mapping cho controller và mapping cho tài nguyên. Các mapping này cần có URL pattern và thứ tự phù hợp.

Ví dụ phân chia URL:

| URL pattern | Thành phần xử lý |
|---|---|
| **/resources/** | Spring MVC resource handler |
| **/booking/** | **FlowHandlerMapping** |
| **/account/** | Controller hoặc handler mapping của ứng dụng |

Khi một URL không được mapping nào nhận, Spring MVC có thể trả 404 hoặc chuyển cho default servlet tùy cấu hình. Không nên dựa vào thứ tự ngẫu nhiên của bean. Hãy xem xét **order** của **FlowHandlerMapping** và các **HandlerMapping** khác để bảo đảm request tài nguyên không bị nhận bởi flow handler hoặc controller tổng quát.

Nếu **DispatcherServlet** được ánh xạ vào **/**, request tài nguyên thường đi qua Spring MVC và resource handler có thể phục vụ chúng. Nếu servlet được ánh xạ vào một pattern mở rộng như **\*.do**, request **/resources/** có thể không đi qua **DispatcherServlet**; khi đó cần cấu hình servlet container hoặc default servlet phù hợp. Spring MVC có **<mvc:default-servlet-handler/>** để chuyển các request không được handler khác xử lý sang default servlet của container trong cấu hình thích hợp.

Không thêm default servlet handler một cách máy móc. Hãy kiểm tra cách triển khai hiện tại, servlet mapping và mục tiêu của từng URL trước khi bật fallback. Nếu mapping đã xử lý tài nguyên bằng **<mvc:resources>** hoặc **ResourceHandlerRegistry**, thường không cần fallback cho chính những URL đó.

## 9. Đường dẫn trong CSS và JavaScript

Đường dẫn được khai báo bên trong CSS được trình duyệt phân giải tương đối với URL của file CSS, không phải URL của trang HTML. Ví dụ:

~~~css
/* File /resources/css/booking.css */
.brand {
    background-image: url("../images/logo.svg");
}
~~~

Với cấu trúc:

~~~text
/resources/
├── css/booking.css
└── images/logo.svg
~~~

đường dẫn **../images/logo.svg** được giải quyết đúng từ vị trí stylesheet. Đây là cách hữu ích để giữ quan hệ thư mục giữa CSS và ảnh.

Tránh dùng URL bắt đầu bằng **/resources/...** trong CSS nếu ứng dụng có thể chạy dưới context path khác root. Đường dẫn bắt đầu bằng **/** vẫn trỏ về root domain. Hãy ưu tiên đường dẫn tương đối giữa các tài nguyên cùng nhóm hoặc một quy trình build tạo URL có prefix theo môi trường.

JavaScript cũng cần cẩn trọng khi gọi endpoint. Nếu script cần gọi một endpoint của ứng dụng, có thể render URL từ view vào một thuộc tính dữ liệu:

~~~jsp
<div id="booking-page"
     data-availability-url="<c:url value='/booking/availability'/>"></div>
~~~

JavaScript đọc giá trị đã được tạo theo context:

~~~javascript
const page = document.getElementById("booking-page");
const availabilityUrl = page.dataset.availabilityUrl;

fetch(availabilityUrl)
    .then(response => {
        if (!response.ok) {
            throw new Error("Không thể kiểm tra tình trạng phòng");
        }
        return response.json();
    })
    .then(data => {
        // Cập nhật giao diện theo kết quả
    });
~~~

Không xây dựng URL endpoint bằng cách nối chuỗi với tên domain hoặc giả định context path luôn rỗng. Cũng cần xử lý lỗi mạng và trạng thái HTTP ở phía trình duyệt; tài nguyên tĩnh tải được không đồng nghĩa endpoint nghiệp vụ luôn sẵn sàng.

## 10. Cache, phiên bản và bảo mật tài nguyên

Tài nguyên tĩnh thường được cache để giảm thời gian tải. Tuy nhiên, nếu thay nội dung CSS hoặc JavaScript mà giữ nguyên URL, trình duyệt có thể tiếp tục dùng bản cũ cho đến khi cache hết hạn.

Một số cách quản lý:

- Dùng tên file có fingerprint hoặc version, ví dụ **booking.a81c2f.css**.
- Khi nội dung thay đổi, phát hành URL mới để trình duyệt tải bản mới.
- Chọn thời hạn cache dài cho tài nguyên có tên chứa fingerprint.
- Chọn thời hạn ngắn hơn cho tài nguyên có URL cố định và thường xuyên thay đổi.
- Không cache dữ liệu cá nhân hoặc nội dung phụ thuộc quyền người dùng như tài nguyên công khai.

**cache-period** trong XML hoặc **setCachePeriod(...)** trong Java là ví dụ cấu hình thời gian cache. Trong hệ thống production, cần xem xét thêm header Cache-Control, quy trình build fingerprint và chính sách CDN nếu có.

Về bảo mật:

- Chỉ cung cấp công khai những file thực sự là tài nguyên tĩnh.
- Không đặt file cấu hình, log, bản sao lưu, khóa bí mật hoặc tài liệu nội bộ trong thư mục được resource handler ánh xạ.
- Giữ view JSP và template phía máy chủ trong vị trí không thể truy cập trực tiếp như **WEB-INF**.
- Cấu hình Spring Security cho phép truy cập các tài nguyên công khai cần thiết, nhưng vẫn bảo vệ endpoint nghiệp vụ và tài nguyên riêng tư.
- Không dùng tên file hoặc đường dẫn do người dùng gửi để tự ghép đường dẫn hệ thống file.

## 11. Các lỗi thường gặp và cách xử lý

### CSS hoặc JavaScript trả về 404 khi triển khai dưới context khác

Kiểm tra URL trong HTML. Nếu URL bắt đầu bằng **/resources/...**, nó có thể bỏ qua context path. Dùng **c:url**, **spring:url** hoặc Thymeleaf **@{...}** để tạo URL theo context.

### Trang hoạt động ở root nhưng lỗi khi đặt dưới context path

Kiểm tra toàn bộ link, form action, script fetch và đường dẫn ảnh. Không chỉ sửa thẻ link; các URL trong JavaScript và CSS cũng có thể đang giả định ứng dụng nằm ở root.

### Tài nguyên bị flow handler nhận nhầm

Kiểm tra URL pattern và thứ tự **HandlerMapping**. Tách prefix tài nguyên khỏi prefix flow và bảo đảm resource handler có thể nhận request tương ứng.

### Tài nguyên không được Spring MVC xử lý

Kiểm tra mapping của **DispatcherServlet**. Nếu servlet chỉ nhận **\*.do** hoặc một prefix khác, request tài nguyên có thể không đi qua servlet đó. Cấu hình default servlet hoặc thay đổi mapping theo kiến trúc ứng dụng.

### File có trong IDE nhưng thiếu trong WAR hoặc JAR

Kiểm tra vị trí source và nội dung artifact đã đóng gói. Tài nguyên trong **src/main/webapp** và **src/main/resources** được đóng gói theo các quy tắc khác nhau; location phải khớp với nơi file thực sự xuất hiện.

### Trình duyệt tiếp tục dùng file cũ

Kiểm tra header cache và URL tài nguyên. Nếu file thay đổi nhưng URL giữ nguyên, áp dụng fingerprint hoặc versioning để tạo URL mới.

### Tài nguyên trả 403

Kiểm tra Spring Security, quyền truy cập của servlet container và quy tắc bảo vệ URL. Chỉ mở công khai các prefix tài nguyên đã xác định; không nới lỏng bảo vệ cho toàn bộ ứng dụng.

## 12. Quy trình kiểm tra sau khi cấu hình

Sau khi khai báo resource handler và cập nhật view, hãy kiểm tra theo thứ tự:

1. Khởi động application context và xác nhận cấu hình MVC, flow mapping và resource handler được tạo thành công.
2. Truy cập trực tiếp URL tài nguyên trong context root và xác nhận trả đúng nội dung, content type và status.
3. Triển khai thử ứng dụng dưới một context path khác root, ví dụ **/booking-portal**.
4. Mở từng view-state của flow và kiểm tra CSS, JavaScript, ảnh, font đều tải được.
5. Gửi form và xác nhận URL flow vẫn được **FlowHandlerMapping** nhận đúng.
6. Kiểm tra endpoint controller và request JavaScript cũng có context path chính xác.
7. Kiểm tra URL tài nguyên không bị chuyển sang flow handler và URL flow không bị resource handler nhận.
8. Kiểm tra header cache sau khi thay đổi file và xác nhận fingerprint/version hoạt động như dự kiến.
9. Thử request tài nguyên không tồn tại và tài nguyên không được phép công khai để xác nhận 404/403 phù hợp.

Có thể dùng tab Network của trình duyệt để xem request URL, status, content type, redirect và cache header. Khi CSS tải về với status 200 nhưng giao diện vẫn sai, kiểm tra nội dung file, đường dẫn ảnh bên trong CSS và lỗi JavaScript trong console.

## 13. Ghi nhớ

Spring MVC cung cấp resource handler để ánh xạ URL đến thư mục tài nguyên web hoặc classpath. Cấu hình có thể dùng **<mvc:resources>** trong XML hoặc **ResourceHandlerRegistry** trong Java. Các view Spring Web Flow dùng chung cơ chế URL của ứng dụng, vì vậy phải tạo đường dẫn có tính đến context path và servlet mapping.

Trong JSP, dùng **c:url** hoặc **spring:url**; trong Thymeleaf, dùng **@{...}**. Tách prefix tài nguyên khỏi prefix flow, kiểm tra thứ tự handler mapping và xác nhận **DispatcherServlet** nhận đúng request. Kết hợp cache versioning, vị trí đóng gói rõ ràng và quy tắc bảo mật sẽ giúp tài nguyên tĩnh hoạt động nhất quán ở mọi môi trường triển khai.

# Cấu hình tự động của Spring Boot và điều kiện kích hoạt

Spring Session cho phép ứng dụng Servlet duy trì HttpSession bằng một kho dữ liệu dùng chung như Redis hoặc JDBC. Khi dùng cùng Spring Boot, phần lớn cấu hình nền tảng có thể được tự động thiết lập: Boot nhận diện thư viện có trên classpath, kiểm tra loại ứng dụng và các bean hạ tầng, sau đó cấu hình repository và bộ lọc tích hợp với Servlet. Hiểu cơ chế này giúp biết vì sao Spring Session được kích hoạt, khi nào cấu hình tự động bỏ qua và cách xử lý khi ứng dụng không dùng đúng kho phiên mong muốn.

Bài học tập trung vào ứng dụng Spring MVC/Servlet và hai kho phổ biến là Redis, JDBC. Spring Session cũng có hỗ trợ các mô hình khác tùy phiên bản và module được dùng. Mô tả dưới đây áp dụng cho cơ chế cấu hình tự động của Spring Boot; tên thuộc tính cụ thể cần đối chiếu với phiên bản Boot trong dự án.

## 1. Cấu hình tự động giải quyết việc gì?

Nếu tự cấu hình Spring Session, lập trình viên phải khai báo repository phù hợp, kết nối đến kho dữ liệu, đăng ký bộ lọc quản lý phiên và liên kết các thiết lập như thời hạn phiên. Cấu hình tự động của Spring Boot giảm phần khai báo lặp lại bằng cách dựa vào những thành phần ứng dụng đã cung cấp.

Trong ứng dụng Servlet, Spring Session cần đưa một lớp tích hợp vào chuỗi xử lý request. Bộ lọc springSessionRepositoryFilter bọc request và response để các lời gọi Servlet API như request.getSession() làm việc với phiên do Spring Session quản lý. Khi request đến, bộ lọc đọc định danh phiên từ cookie hoặc cơ chế phân giải ID đã cấu hình, sau đó repository tìm dữ liệu phiên trong kho lưu trữ. Khi response hoàn tất, thay đổi phiên được ghi theo chính sách lưu của repository.

Có thể hình dung luồng khởi động như sau:

    1. @SpringBootApplication bật cơ chế auto-configuration thông qua @EnableAutoConfiguration.
    2. Spring Boot tìm các lớp cấu hình tự động được đăng ký bởi những thư viện có trên classpath.
    3. Các điều kiện về môi trường Servlet, lớp thư viện, thuộc tính và bean hiện có được đánh giá.
    4. Nếu một cấu hình Spring Session phù hợp được chọn, Boot tạo hoặc kích hoạt các thành phần cần thiết, gồm repository và bộ lọc tích hợp.
    5. Khi ứng dụng nhận request, bộ lọc kết nối HttpSession của Servlet với repository đã chọn.

Cấu hình tự động không tự tạo ra một Redis server hoặc một cơ sở dữ liệu. Ứng dụng vẫn phải cung cấp dịch vụ lưu trữ, thông tin kết nối và quyền truy cập phù hợp.

## 2. Điều kiện chung để Spring Session được kích hoạt

Không có một điều kiện đơn lẻ bảo đảm Spring Session sẽ hoạt động. Cấu hình tự động được quyết định bởi một nhóm điều kiện liên quan với nhau.

### 2.1. Ứng dụng phải chạy đúng mô hình web

Nội dung của bài này áp dụng cho ứng dụng Servlet, thường là Spring MVC chạy trên embedded Tomcat, Jetty hoặc Undertow. Spring Session tích hợp với Servlet bằng HttpSession và SessionRepositoryFilter.

Ứng dụng WebFlux dùng API WebSession và cơ chế tích hợp reactive tương ứng. Không nên lấy cấu hình HttpSession của Servlet áp dụng nguyên xi cho WebFlux. Trước khi điều tra cấu hình, hãy xác định ứng dụng đang khởi tạo web application context loại nào.

### 2.2. Module Spring Session phù hợp phải có trên classpath

Boot chỉ có thể tự cấu hình một kiểu repository khi module triển khai tương ứng hiện diện. Ví dụ:

- Redis cần module spring-session-data-redis.
- JDBC cần module spring-session-jdbc.

Các module Spring Session cung cấp khả năng tích hợp repository với kho dữ liệu tương ứng. Starter của kho dữ liệu cung cấp các thành phần kết nối như RedisConnectionFactory hoặc DataSource, nhưng chỉ có starter Redis/JDBC không đồng nghĩa đã có module Spring Session cho kho đó.

Thông thường dự án cũng khai báo starter dữ liệu của Boot để có cấu hình kết nối và các thư viện nền tảng. Cần kiểm tra dependency tree khi nghi ngờ một module bị thiếu hoặc có phiên bản không tương thích.

### 2.3. Hạ tầng kết nối phải sẵn sàng

Đối với Redis, ứng dụng cần có RedisConnectionFactory hoạt động và thông tin kết nối hợp lệ. Đối với JDBC, ứng dụng cần có DataSource trỏ đến cơ sở dữ liệu có thể truy cập. Cấu hình tự động có thể tạo một số bean hạ tầng nếu starter và thuộc tính tương ứng được cung cấp; nếu ứng dụng đã tự khai báo bean, Boot thường sử dụng bean đó theo các điều kiện áp dụng.

Có thư viện trên classpath nhưng không có kết nối hợp lệ vẫn có thể khiến ứng dụng khởi động lỗi hoặc lỗi khi thao tác với phiên. Cần phân biệt lỗi cấu hình bean với lỗi kết nối dịch vụ bên ngoài.

### 2.4. Loại kho phiên được chọn phải phù hợp

Nếu chỉ có một module Spring Session được hỗ trợ trên classpath, Boot có thể nhận diện và chọn cấu hình tương ứng theo quy tắc của phiên bản đang dùng. Khi có nhiều lựa chọn cùng hiện diện, nên khai báo rõ loại kho phiên bằng spring.session.store-type để kết quả khởi động dễ dự đoán.

Ví dụ:

- spring.session.store-type=redis yêu cầu dùng repository Redis.
- spring.session.store-type=jdbc yêu cầu dùng repository JDBC.
- spring.session.store-type=none tắt cấu hình tự động kho phiên của Boot trong các phiên bản hỗ trợ giá trị này.

Không nên dựa vào thứ tự dependency để phỏng đoán kho nào được chọn. Hãy kiểm tra thuộc tính cấu hình và báo cáo điều kiện auto-configuration của đúng phiên bản Boot.

### 2.5. Cấu hình tự động không bị cấu hình tùy chỉnh thay thế

Spring Boot được thiết kế để lùi lại khi ứng dụng đã cung cấp bean tương ứng. Ví dụ, một SessionRepository do ứng dụng tự khai báo có thể khiến cấu hình repository mặc định không còn được áp dụng. Đây là hành vi có chủ đích để ứng dụng có thể tùy chỉnh.

Điều đó cũng có nghĩa một bean tự khai báo sai hoặc một cấu hình thủ công không đầy đủ có thể làm Boot không tạo thành phần mà lập trình viên mong đợi. Khi cấu hình tự động không xuất hiện, hãy tìm bean tùy chỉnh và các annotation bật Spring Session trong mã nguồn cấu hình ứng dụng.

## 3. Ví dụ cấu hình tự động với Redis

Với ứng dụng Servlet dùng Redis, dự án thường cần module Spring Session Redis và starter Redis của Spring Boot. Ví dụ khai báo dependency Gradle:

    dependencies {
        implementation("org.springframework.boot:spring-boot-starter-web")
        implementation("org.springframework.boot:spring-boot-starter-data-redis")
        implementation("org.springframework.session:spring-session-data-redis")
    }

Các phiên bản dependency cần được quản lý đồng bộ bằng Spring Boot dependency management hoặc một BOM tương thích. Tránh tự ghép các phiên bản Spring Framework, Spring Session và Spring Boot không cùng hệ tương thích.

Một cấu hình tối thiểu trong application.yml có thể là:

    spring:
      data:
        redis:
          host: localhost
          port: 6379
      session:
        store-type: redis
        timeout: 30m
        redis:
          namespace: demo:session
          flush-mode: on-save

Ý nghĩa của các thuộc tính:

| Thuộc tính | Vai trò |
|---|---|
| spring.data.redis.host | Máy chủ Redis mà ứng dụng kết nối |
| spring.data.redis.port | Cổng Redis |
| spring.session.store-type | Chỉ định repository phiên cần dùng |
| spring.session.timeout | Thời gian không hoạt động tối đa của phiên |
| spring.session.redis.namespace | Tiền tố namespace để phân vùng khóa phiên trong Redis |
| spring.session.redis.flush-mode | Quy định thời điểm thay đổi phiên được ghi xuống kho |

Tên thuộc tính kết nối Redis có thể khác giữa các dòng Spring Boot cũ và mới. Hãy dùng metadata cấu hình hoặc tài liệu của đúng phiên bản dự án khi chuyển phiên bản.

Sau khi khởi động, nếu các điều kiện phù hợp, Boot thiết lập tích hợp Spring Session Redis. Ứng dụng có thể tiếp tục sử dụng Servlet API:

    @GetMapping("/cart")
    public String addItem(HttpServletRequest request) {
        HttpSession session = request.getSession();
        Integer count = (Integer) session.getAttribute("itemCount");

        session.setAttribute("itemCount", count == null ? 1 : count + 1);
        return "redirect:/cart/view";
    }

Đoạn mã trên chỉ minh họa việc dùng HttpSession; trong ứng dụng thật, controller nên dùng service để quản lý giỏ hàng và kiểm soát dữ liệu đầu vào. Điểm cần chú ý là code nghiệp vụ vẫn thao tác qua API Servlet, còn Spring Session đảm nhiệm việc lưu phiên thông qua repository Redis.

## 4. Ví dụ cấu hình tự động với JDBC

Với JDBC, dự án cần module Spring Session JDBC, starter JDBC và một DataSource có thể kết nối đến cơ sở dữ liệu. Ví dụ:

    dependencies {
        implementation("org.springframework.boot:spring-boot-starter-web")
        implementation("org.springframework.boot:spring-boot-starter-jdbc")
        implementation("org.springframework.session:spring-session-jdbc")
        runtimeOnly("org.postgresql:postgresql")
    }

Ví dụ cấu hình:

    spring:
      datasource:
        url: jdbc:postgresql://localhost:5432/session_demo
        username: session_app
        password: ${SESSION_DB_PASSWORD}
      session:
        store-type: jdbc
        timeout: 30m
        jdbc:
          initialize-schema: embedded

Spring Session JDBC sử dụng các bảng để lưu thông tin phiên và thuộc tính phiên. Với cấu hình khởi tạo schema tự động, cần hiểu chính xác giá trị thuộc tính và giới hạn của nó trong phiên bản đang sử dụng. Trong môi trường production, thường nên quản lý schema bằng công cụ migration của dự án, kiểm soát quyền tạo/sửa bảng và triển khai schema trước khi ứng dụng nhận lưu lượng.

Khi repository JDBC được cấu hình, ứng dụng Servlet vẫn thao tác với HttpSession như bình thường. Dữ liệu phiên được đọc và ghi qua DataSource thay vì chỉ nằm trong bộ nhớ của một instance.

Không nên dùng chung tài khoản cơ sở dữ liệu có quyền quản trị cho ứng dụng chỉ để Spring Session tạo bảng. Hãy cấp quyền tối thiểu cần thiết cho việc đọc, ghi, cập nhật và xóa dữ liệu phiên.

## 5. Cách Boot đánh giá điều kiện auto-configuration

Cấu hình tự động của Boot được tạo từ các lớp cấu hình được đăng ký bởi thư viện. Những lớp đó thường dùng các điều kiện để chỉ kích hoạt khi môi trường đáp ứng yêu cầu. Các điều kiện thường gặp gồm:

| Nhóm điều kiện | Câu hỏi cần kiểm tra | Ví dụ trong cấu hình Spring Session |
|---|---|---|
| Điều kiện classpath | Có lớp hoặc module cần thiết không? | Module Spring Session Redis hoặc JDBC có được đóng gói không? |
| Điều kiện loại ứng dụng | Đây có phải ứng dụng Servlet phù hợp không? | Ứng dụng có Servlet web application context không? |
| Điều kiện bean | Bean hạ tầng hoặc repository đã có chưa? | Có RedisConnectionFactory, DataSource, hoặc repository tùy chỉnh không? |
| Điều kiện thuộc tính | Thuộc tính có bật, tắt hoặc chọn cấu hình nào không? | spring.session.store-type chọn Redis/JDBC hoặc none |
| Điều kiện bean còn thiếu | Ứng dụng đã tự cung cấp bean thay thế chưa? | Boot lùi lại khi bean do ứng dụng khai báo đáp ứng điều kiện |

Các điều kiện này thường được thể hiện bằng những annotation như @ConditionalOnClass, @ConditionalOnBean, @ConditionalOnProperty và @ConditionalOnMissingBean. Đây là cách Boot giới hạn phạm vi kích hoạt cấu hình, không phải các annotation mà ứng dụng phải tự thêm vào để Spring Session hoạt động.

Có thể hiểu quá trình lựa chọn bằng sơ đồ:

    @SpringBootApplication
             |
             v
    Nạp các cấu hình tự động
             |
             v
    Ứng dụng Servlet phù hợp?
        | Không -> Không dùng cấu hình HttpSession này
        | Có
        v
    Module Spring Session có trên classpath?
        | Không -> Không có repository tương ứng để tự cấu hình
        | Có
        v
    Chọn store và kiểm tra hạ tầng
        | Redis -> RedisConnectionFactory
        | JDBC  -> DataSource
        v
    Có bean tùy chỉnh khiến auto-config lùi lại?
        | Có -> Dùng cấu hình/bean do ứng dụng cung cấp
        | Không
        v
    Cấu hình repository và bộ lọc Spring Session

Sơ đồ là mô hình khái niệm. Thứ tự và điều kiện chính xác phụ thuộc vào phiên bản Boot và module Spring Session trên classpath.

## 6. @SpringBootApplication và các annotation bật Spring Session

Trong ứng dụng Spring Boot, @SpringBootApplication thường đã bao gồm @EnableAutoConfiguration, nên không cần thêm annotation này lần nữa. Khi dependency và điều kiện phù hợp, Boot có thể cấu hình Spring Session tự động.

Trong cấu hình Java thủ công, Spring Session cũng cung cấp các annotation như @EnableRedisHttpSession, @EnableJdbcHttpSession hoặc @EnableSpringHttpSession tùy cách tích hợp. Những annotation này cho phép ứng dụng bật và tùy chỉnh Spring Session rõ ràng, nhưng thường được dùng khi muốn tự kiểm soát cấu hình repository.

Không nên vừa dựa vào cấu hình tự động của Boot vừa khai báo một cấu hình bật repository thủ công mà không hiểu các bean được tạo ra. Hai cơ chế có thể cạnh tranh hoặc khiến một phần cấu hình tự động lùi lại. Chọn một cách cấu hình rõ ràng, rồi xác minh repository và filter thực tế trong application context.

Nếu cần tùy chỉnh hành vi mà Boot đã hỗ trợ bằng thuộc tính, ưu tiên cấu hình qua spring.session.*. Nếu cần một repository hoặc cách phân giải session ID đặc biệt, hãy xem xét cấu hình Java tùy chỉnh và xác nhận những bean mặc định nào sẽ được thay thế.

## 7. Vì sao cấu hình tự động có thể không kích hoạt?

Một số nguyên nhân thường gặp:

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Request vẫn dùng session mặc định trong bộ nhớ của container | Module Spring Session chưa có hoặc không được chọn | Kiểm tra dependency spring-session-data-redis hoặc spring-session-jdbc và báo cáo điều kiện |
| Chọn Redis nhưng ứng dụng không khởi tạo được repository | Thiếu RedisConnectionFactory, cấu hình kết nối sai hoặc Redis không truy cập được | Kiểm tra bean kết nối, host, port, mật khẩu, TLS và trạng thái Redis |
| Chọn JDBC nhưng không tìm thấy bảng | Schema chưa được tạo hoặc migration chưa chạy | Kiểm tra DataSource, schema và quyền truy cập bảng |
| Có nhiều module lưu phiên nhưng Boot chọn khác dự kiến | Không khai báo rõ loại store hoặc thuộc tính không được nạp | Kiểm tra profile, file cấu hình và spring.session.store-type |
| Boot không tạo bean mặc định | Ứng dụng đã khai báo bean tùy chỉnh khiến auto-config lùi lại | Tìm SessionRepository, cấu hình @Enable...HttpSession và các bean liên quan |
| Cấu hình Servlet không có tác dụng | Ứng dụng đang chạy WebFlux hoặc loại application context khác | Kiểm tra starter web và loại web application context |
| Thay đổi thuộc tính nhưng hành vi không đổi | Thuộc tính đặt sai prefix, sai profile hoặc bị nguồn cấu hình khác ghi đè | Kiểm tra cấu hình hiệu lực và log lúc khởi động |

Cần phân biệt hai nhóm lỗi. **Không kích hoạt cấu hình** thường liên quan đến classpath, điều kiện hoặc bean. **Đã kích hoạt nhưng không truy cập được kho dữ liệu** thường liên quan đến mạng, thông tin xác thực, schema, quyền hoặc dịch vụ lưu trữ. Cách điều tra khác nhau nên không nên chỉ nhìn một lỗi kết nối rồi kết luận auto-configuration không chạy.

## 8. Kiểm tra điều kiện đã được thỏa mãn

Spring Boot có thể in báo cáo điều kiện auto-configuration khi khởi động với tùy chọn --debug. Báo cáo cho biết cấu hình nào khớp và cấu hình nào bị loại, cùng lý do. Đây là điểm bắt đầu hữu ích khi ứng dụng không tạo repository như mong đợi.

Có thể kiểm tra theo trình tự:

1. Xác nhận dependency runtime có module Spring Session tương ứng và phiên bản tương thích.
2. Xác nhận ứng dụng là Servlet hoặc WebFlux để chọn đúng cơ chế phiên.
3. Kiểm tra cấu hình hiệu lực: loại store, timeout, namespace và thông tin kết nối.
4. Đọc báo cáo điều kiện khi khởi động để xem cấu hình Spring Session có match hay không.
5. Kiểm tra các bean trong application context, đặc biệt repository và bộ lọc tích hợp.
6. Thực hiện request thử, gửi cookie phiên ở request tiếp theo và xác nhận dữ liệu phiên được khôi phục.
7. Nếu chạy nhiều instance, gửi các request liên tiếp qua các instance khác nhau để xác nhận chúng cùng dùng một repository.

Nếu ứng dụng có Spring Boot Actuator, endpoint conditions có thể hỗ trợ xem báo cáo điều kiện khi endpoint được bật và expose an toàn. Không nên expose thông tin chẩn đoán nhạy cảm ra Internet công khai. Trong môi trường production, chỉ cấp quyền truy cập cho người vận hành có thẩm quyền.

## 9. Kiểm thử hành vi thay vì chỉ kiểm tra ứng dụng khởi động

Một ứng dụng khởi động thành công chưa chứng minh phiên được lưu đúng nơi. Nên kiểm tra hành vi HTTP thực tế:

- Request đầu tiên tạo phiên và ghi một thuộc tính thử nghiệm.
- Lấy cookie session ID từ response.
- Request thứ hai gửi lại cookie đó và đọc được thuộc tính đã lưu.
- Khởi động lại một instance rồi gửi lại cookie để kiểm tra dữ liệu có còn trong kho chia sẻ.
- Trong môi trường nhiều instance, định tuyến hai request đến hai instance khác nhau và xác nhận chúng khôi phục cùng một phiên.
- Hết thời hạn không hoạt động rồi gửi lại cookie để xác nhận phiên hết hạn theo cấu hình.

Khi viết kiểm thử tích hợp, có thể dùng MockMvc để kiểm tra hành vi Servlet trong application context, hoặc chạy kiểm thử với Redis/JDBC thật thông qua môi trường test phù hợp. Với bài kiểm thử cần xác nhận TTL, schema, transaction hay tính tương thích giữa nhiều instance, kho dữ liệu thực tế sẽ cho bằng chứng đáng tin cậy hơn một mock repository.

Không đưa session ID thật vào log kiểm thử hoặc báo cáo. Khi so sánh request, chỉ cần xác nhận cookie được gửi lại và cùng một phiên được khôi phục.

## 10. Lưu ý khi triển khai nhiều instance

Tự động cấu hình ở từng instance không bảo đảm chúng cùng dùng một kho dữ liệu. Mọi instance phải có cấu hình tương thích về loại repository, địa chỉ kho dữ liệu, namespace, serializer và các thiết lập liên quan. Nếu mỗi instance dùng Redis khác nhau hoặc namespace khác nhau, cùng một cookie có thể không tìm được cùng phiên khi request được chuyển sang instance khác.

Cũng cần theo dõi sức khỏe và khả năng phục hồi của kho phiên. Redis hoặc cơ sở dữ liệu gặp sự cố có thể làm request không đọc hoặc ghi được phiên. Chính sách xử lý khi kho phiên không sẵn sàng phải phù hợp với mức độ nhạy cảm của ứng dụng. Không tự động hạ cấp sang session cục bộ của container nếu điều đó khiến trạng thái đăng nhập hoặc giỏ hàng thay đổi giữa các instance mà không được kiểm soát.

Các thiết lập timeout, flush mode, namespace và cookie cũng cần thống nhất. Đặc biệt, cookie chỉ mang định danh phiên; TTL và dữ liệu phiên nằm ở repository. Đổi tên namespace hoặc chuyển loại store cần có kế hoạch chuyển đổi vì các phiên cũ có thể không còn được tìm thấy.

## Kết luận

Spring Boot tự động cấu hình Spring Session khi ứng dụng, module lưu trữ, hạ tầng và thuộc tính thỏa mãn các điều kiện tương ứng. Với Redis hoặc JDBC, cần có module Spring Session chuyên biệt cùng kết nối dữ liệu hợp lệ; spring.session.store-type giúp lựa chọn rõ ràng khi cần. Cấu hình tự động có thể lùi lại khi ứng dụng tự khai báo bean hoặc bật cấu hình thủ công. Khi điều tra, hãy kiểm tra classpath, loại ứng dụng, thuộc tính hiệu lực, báo cáo điều kiện, repository và bộ lọc thực tế, rồi xác nhận bằng request qua cùng cookie. Cách tiếp cận đó giúp xác định chính xác Spring Session đã được kích hoạt và đang lưu phiên ở đâu trong hệ thống.

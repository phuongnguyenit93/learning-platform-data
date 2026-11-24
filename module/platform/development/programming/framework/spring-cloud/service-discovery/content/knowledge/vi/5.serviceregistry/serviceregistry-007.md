# Điều khiển trạng thái qua Actuator serviceregistry

Trong kiến trúc microservice, một instance có thể vẫn chạy bình thường nhưng cần tạm ngừng nhận request để bảo trì, triển khai phiên bản mới hoặc xử lý sự cố. Spring Cloud Commons cung cấp abstraction ServiceRegistry và một Actuator endpoint có ID là serviceregistry để đọc hoặc thay đổi trạng thái đăng ký của instance hiện tại.

Endpoint này tạo một kênh điều khiển trạng thái ở mức registry. Nó không dừng tiến trình ứng dụng, không tự chờ request đang xử lý kết thúc và cũng không thay thế health check. Muốn dùng an toàn, cần hiểu trạng thái mà registry hỗ trợ, cách client lọc instance và thời gian cập nhật cache của hệ thống.

## 1. ServiceRegistry và Registration

Spring Cloud Commons định nghĩa ServiceRegistry như một abstraction để các thành phần ứng dụng thao tác với registry mà không phải gọi API riêng của Eureka, Consul hoặc ZooKeeper trực tiếp. Registration biểu diễn thông tin đăng ký của một instance, chẳng hạn service ID, instance ID, host, port và metadata.

Các thao tác cốt lõi của ServiceRegistry gồm:

| Thao tác | Ý nghĩa |
|---|---|
| register | Đăng ký instance vào registry |
| deregister | Hủy đăng ký instance khỏi registry |
| setStatus | Thay đổi trạng thái của registration hiện tại |
| getStatus | Đọc trạng thái của registration hiện tại |
| close | Giải phóng tài nguyên mà implementation quản lý |

Mỗi nhà cung cấp có implementation riêng, ví dụ EurekaServiceRegistry hoặc ConsulServiceRegistry. Vì vậy, ServiceRegistry thống nhất cách gọi nhưng không bắt buộc mọi registry dùng cùng một tập giá trị trạng thái hoặc cùng một cách lưu trạng thái.

Thông thường, Spring Cloud tự động đăng ký instance khi ứng dụng khởi động nếu discovery implementation tương ứng có mặt trên classpath. Có thể tắt auto-registration bằng cấu hình:

    spring:
      cloud:
        service-registry:
          auto-registration:
            enabled: false

Một cách khác là dùng @EnableDiscoveryClient(autoRegister = false). Khi tắt auto-registration, ứng dụng cần có quy trình đăng ký riêng nếu vẫn muốn xuất hiện trong registry. Các sự kiện InstancePreRegisteredEvent và InstanceRegisteredEvent gắn với luồng auto-registration sẽ không được phát khi auto-registration bị tắt.

## 2. Actuator endpoint serviceregistry

Spring Cloud Commons cung cấp endpoint Actuator có ID là serviceregistry. Endpoint dựa trên ServiceRegistry và Registration bean trong Spring Application Context.

Với management base path mặc định của Spring Boot là /actuator, URL HTTP mặc định là:

    /actuator/serviceregistry

Endpoint có hai thao tác chính:

- GET đọc trạng thái registration hiện tại.
- POST gửi trạng thái mới để implementation của ServiceRegistry cập nhật registration.

Request POST phải có JSON body chứa trường status. Ví dụ:

    {
      "status": "OUT_OF_SERVICE"
    }

Giá trị OUT_OF_SERVICE trong ví dụ chỉ là một trạng thái thường gặp; giá trị hợp lệ phải theo registry đang dùng. Không nên lấy nguyên danh sách trạng thái của Eureka rồi gửi sang Consul hoặc một provider khác mà chưa kiểm tra tài liệu của provider đó.

Endpoint này cần có ServiceRegistry implementation và Registration bean trong application context. Nếu không có registration tương ứng, endpoint không thể điều khiển một instance cụ thể. Ngoài ra, endpoint phải được expose qua HTTP thì client mới gọi được.

## 3. Expose endpoint trong Spring Boot

Spring Boot không expose tất cả Actuator endpoint qua HTTP theo mặc định. Hãy thêm serviceregistry vào danh sách endpoint cần expose trong application.yml:

    management:
      endpoints:
        web:
          exposure:
            include: health,info,serviceregistry

Nếu ứng dụng đã có danh sách exposure, hãy thêm serviceregistry vào danh sách hiện tại thay vì ghi đè các endpoint cần thiết khác. Endpoint ID được viết liền là serviceregistry; path mặc định cũng dùng tên này.

Có thể tùy chỉnh base path:

    management:
      endpoints:
        web:
          base-path: /manage
          exposure:
            include: health,serviceregistry

Khi đó URL trở thành /manage/serviceregistry. Nếu management server chạy trên cổng riêng, hãy gọi đúng cổng management:

    server:
      port: 8080

    management:
      server:
        port: 8081
      endpoints:
        web:
          exposure:
            include: health,serviceregistry

Trong ví dụ trên, request nghiệp vụ dùng cổng 8080, còn endpoint quản trị dùng cổng 8081. Cần kiểm soát riêng khả năng truy cập cổng quản trị vì POST có thể thay đổi việc instance có nhận traffic hay không.

## 4. Đọc trạng thái hiện tại bằng GET

Trước khi thay đổi trạng thái, nên đọc trạng thái đang có để xác định đúng instance và ghi nhận giá trị ban đầu.

Ví dụ dùng curl:

    curl -i http://localhost:8080/actuator/serviceregistry

Một response minh họa:

    HTTP/1.1 200
    Content-Type: application/vnd.spring-boot.actuator.v3+json

    {
      "status": "UP"
    }

Nội dung response cụ thể phụ thuộc ServiceRegistry implementation và phiên bản Spring Cloud. Một số provider hoặc phiên bản có thể trả thêm trường trạng thái khác. Hãy coi response thực tế của ứng dụng là nguồn xác nhận, không giả định mọi provider đều trả cùng cấu trúc.

Nếu nhận 404, kiểm tra các nguyên nhân thường gặp:

- Chưa có discovery starter hoặc ServiceRegistry bean trong application context.
- Registration bean chưa được tạo hoặc service chưa đăng ký.
- Endpoint serviceregistry chưa được expose.
- Management base path, port hoặc path mapping khác với URL đang gọi.
- Endpoint bị tắt hoặc cấu hình security che giấu endpoint.

Nếu nhận 401 hoặc 403, request đã tới lớp bảo mật nhưng chưa có quyền phù hợp. Kiểm tra authentication, authorization và CSRF policy.

## 5. Thay đổi trạng thái bằng POST

Để chuyển instance sang trạng thái bảo trì, gửi POST với JSON body:

    curl -i -X POST http://localhost:8080/actuator/serviceregistry \
      -H "Content-Type: application/json" \
      -d "{\"status\":\"OUT_OF_SERVICE\"}"

Để đưa instance trở lại phục vụ, gửi trạng thái phù hợp với provider, ví dụ Eureka:

    curl -i -X POST http://localhost:8080/actuator/serviceregistry \
      -H "Content-Type: application/json" \
      -d "{\"status\":\"UP\"}"

POST gọi ServiceRegistry.setStatus(registration, status). Endpoint không tự diễn giải ý nghĩa nghiệp vụ của chuỗi trạng thái; implementation của provider quyết định cách áp dụng và giá trị nào được chấp nhận. Nếu gửi giá trị không hợp lệ, provider có thể ném lỗi hoặc trả response lỗi.

Sau khi POST, hãy gọi GET lần nữa để xác minh trạng thái mà provider trả về. Nếu muốn xác nhận instance đã được loại khỏi luồng traffic, cần kiểm tra thêm registry và kết quả tra cứu từ client hoặc LoadBalancer.

## 6. Trạng thái phụ thuộc registry

### Eureka

Eureka hỗ trợ các trạng thái instance phổ biến:

| Trạng thái | Ý nghĩa |
|---|---|
| UP | Instance đang phục vụ |
| DOWN | Instance không khỏe hoặc không thể phục vụ |
| OUT_OF_SERVICE | Instance được chủ động đưa ra khỏi luồng phục vụ |
| UNKNOWN | Trạng thái chưa xác định |

Eureka client mặc định chủ yếu dùng heartbeat để xác định instance còn hoạt động. Nếu không bật tích hợp health check, trạng thái Actuator của ứng dụng không tự động được truyền sang Eureka; sau khi đăng ký thành công, instance có thể tiếp tục được quảng bá là UP dù health endpoint báo trạng thái khác.

Để truyền trạng thái sức khỏe ứng dụng tới Eureka, cấu hình trong application.yml:

    eureka:
      client:
        healthcheck:
          enabled: true

Khi health check integration được bật, trạng thái sức khỏe hiện tại của ứng dụng có thể ảnh hưởng trạng thái instance trong Eureka. Vì vậy, cần phân biệt thay đổi thủ công qua serviceregistry với trạng thái do HealthCheckHandler tạo ra. Một cơ chế tự động cập nhật trạng thái có thể tác động tới kết quả của thao tác thủ công; hãy kiểm thử hành vi trong phiên bản đang dùng.

Eureka loại các instance không ở trạng thái UP khỏi kết quả discovery mặc định của client. Điều này hữu ích cho bảo trì có kế hoạch: instance vẫn còn registration trong server nhưng không được xem là instance đang sẵn sàng phục vụ.

Spring Cloud Netflix cũng có các endpoint pause và resume. Khi các endpoint này được bật, pause đưa instance Eureka sang OUT_OF_SERVICE; resume gỡ trạng thái ghi đè để instance trở lại trạng thái do ứng dụng báo sau heartbeat tiếp theo. Đây là cơ chế vòng đời riêng, không phải tên khác của endpoint serviceregistry.

### Consul

Consul quản lý trạng thái service thông qua health check và các trạng thái vận hành của agent. Spring Cloud Consul thường đăng ký HTTP health check gọi endpoint /actuator/health. Nếu check thất bại, instance có thể chuyển sang critical trong Consul.

Không đồng nhất trạng thái của endpoint serviceregistry với trạng thái health check. Health check phản ánh kết quả kiểm tra endpoint; trạng thái bảo trì là tín hiệu điều khiển instance. Một implementation Consul có thể ánh xạ thao tác setStatus sang maintenance mode của service. Các status được chấp nhận và cách getStatus trả về phụ thuộc phiên bản Spring Cloud Consul. Kiểm tra đúng implementation đang chạy trước khi tự động hóa thao tác.

Ví dụ cấu hình health check Consul độc lập với endpoint serviceregistry:

    spring:
      cloud:
        consul:
          discovery:
            register: true
            register-health-check: true
            health-check-path: /actuator/health
            health-check-interval: 10s

Đặt instance vào maintenance mode không đồng nghĩa với việc health endpoint đã chuyển DOWN. Ngược lại, health check chuyển critical cũng không nhất thiết có nghĩa một quản trị viên đã chủ động đặt instance vào maintenance mode. Cần quan sát cả trạng thái check và trạng thái service trong Consul.

### ZooKeeper

Spring Cloud Zookeeper cũng triển khai ServiceRegistry. Tài liệu Spring Cloud mô tả khả năng đặt OUT_OF_SERVICE bằng metadata của instance; Spring Cloud LoadBalancer có thể lọc các instance có status khác UP. Tuy nhiên, cơ chế lọc này phụ thuộc service instance list supplier được sử dụng. Không nên giả định mọi client ZooKeeper hoặc mọi recipe đều áp dụng cách lọc giống nhau.

## 7. Quy trình đưa instance ra khỏi traffic để bảo trì

Một quy trình bảo trì nên kiểm soát cả registry, client cache và request đang xử lý. Ví dụ với provider hỗ trợ OUT_OF_SERVICE:

1. **Xác định đúng instance:** xác nhận host, port, instance ID và application name để tránh thay đổi nhầm instance.
2. **Đọc trạng thái hiện tại:** gọi GET /actuator/serviceregistry và lưu lại response.
3. **Đưa instance ra khỏi phục vụ:** POST status OUT_OF_SERVICE nếu provider hỗ trợ.
4. **Xác minh ở registry:** kiểm tra giao diện hoặc API của registry để xác nhận trạng thái đã được cập nhật.
5. **Chờ client cập nhật:** client discovery thường có cache hoặc chu kỳ làm mới; kiểm tra danh sách instance từ phía consumer trước khi dừng tiến trình.
6. **Drain request:** chờ request đang xử lý hoàn tất theo cơ chế của ứng dụng, gateway hoặc nền tảng triển khai.
7. **Thực hiện bảo trì:** cập nhật, khởi động lại hoặc thay đổi cấu hình instance.
8. **Đưa instance trở lại:** POST UP theo quy ước của provider, sau đó xác minh trạng thái registry, health check và khả năng nhận request.

Không có một thời gian chờ cố định áp dụng cho mọi hệ thống. Thời gian client nhận ra trạng thái mới phụ thuộc registry, cache discovery, chu kỳ refresh và LoadBalancer. Chỉ thấy POST trả thành công chưa chứng minh mọi consumer đã ngừng gửi request tới instance.

Nếu cần ngừng hẳn một instance, deregister là thao tác khác với setStatus. OUT_OF_SERVICE giữ registration nhưng đánh dấu instance không nên nhận traffic; deregister xóa registration khỏi registry. Việc dừng process cũng là hành động riêng và cần thực hiện sau khi drain hoàn tất.

## 8. Phân biệt serviceregistry, health và deregister

Ba thao tác sau giải quyết ba câu hỏi khác nhau:

| Cơ chế | Mục đích | Ví dụ |
|---|---|---|
| Actuator health | Ứng dụng có khỏe hoặc sẵn sàng không? | GET /actuator/health |
| Actuator serviceregistry | Registration hiện tại có trạng thái gì và cần đổi sang trạng thái nào? | GET/POST /actuator/serviceregistry |
| ServiceRegistry.deregister | Xóa registration khỏi registry | Hủy đăng ký instance khi kết thúc vòng đời |

Ví dụ, ứng dụng có thể trả health UP nhưng registration đang OUT_OF_SERVICE vì đang bảo trì. Đây là trạng thái hợp lệ: tiến trình còn sống, nhưng quản trị viên chủ động không cho consumer chọn instance.

Ngược lại, nếu health DOWN nhưng registration vẫn UP, consumer có thể tiếp tục nhận instance tùy cách registry và discovery client xử lý health. Cần bật và cấu hình health integration phù hợp, đồng thời xác minh hành vi thực tế.

Không dùng POST serviceregistry như một cách thay thế cho việc sửa health indicator. Nếu ứng dụng thực sự không khỏe, hãy xử lý nguyên nhân sức khỏe. Nếu ứng dụng khỏe nhưng cần bảo trì, dùng trạng thái bảo trì được provider hỗ trợ.

## 9. Bảo mật endpoint điều khiển trạng thái

POST serviceregistry có thể ảnh hưởng trực tiếp đến khả năng phục vụ của hệ thống. Người không được phép có thể đưa instance khỏe sang OUT_OF_SERVICE hoặc khôi phục một instance chưa sẵn sàng. Vì vậy, endpoint cần được bảo vệ như một API quản trị.

Các nguyên tắc cần áp dụng:

- Chỉ expose serviceregistry khi có nhu cầu vận hành thực tế.
- Đặt management endpoint trên mạng nội bộ hoặc management port được kiểm soát.
- Dùng HTTPS khi request đi qua mạng không tin cậy.
- Yêu cầu xác thực và phân quyền riêng cho thao tác thay đổi trạng thái.
- Giới hạn quyền POST cho vai trò vận hành phù hợp; người dùng chỉ quan sát có thể chỉ cần GET.
- Nếu Spring Security bật CSRF protection, cấu hình client quản trị để gửi CSRF token hoặc thiết lập ngoại lệ hẹp, có chủ đích cho API machine-to-machine.
- Ghi log người thực hiện, instance ID, trạng thái cũ, trạng thái mới, thời điểm và kết quả thao tác.
- Không đưa credential vào shell history, script dùng chung hoặc repository.

Expose endpoint trong management.endpoints.web.exposure.include chỉ làm endpoint có thể truy cập qua web; cấu hình đó không tự cấp quyền an toàn. Cần kiểm tra cả authentication, authorization, network policy và TLS.

## 10. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| GET serviceregistry trả 404 | Endpoint chưa expose hoặc thiếu Registration bean | Kiểm tra dependency discovery, registration và exposure |
| POST trả 404 | Sai management base path hoặc endpoint ID | Xác nhận URL thực tế và dùng path serviceregistry |
| POST trả 400 | JSON sai cấu trúc hoặc thiếu trường status | Gửi JSON có trường status dạng chuỗi |
| POST trả 500 | Provider từ chối status hoặc không liên lạc được registry | Đọc log ứng dụng và log registry client |
| GET trả trạng thái khác mong đợi | Status mapping riêng của provider | Kiểm tra ServiceRegistry implementation và registry UI/API |
| POST thành công nhưng consumer vẫn gọi instance | Cache chưa refresh hoặc provider không loại instance khỏi kết quả | Kiểm tra registry, DiscoveryClient cache và LoadBalancer supplier |
| Instance tự quay lại UP | Health integration hoặc heartbeat cập nhật lại trạng thái | Kiểm tra Eureka HealthCheckHandler, heartbeat và cơ chế provider |
| Instance vẫn không phục vụ sau khi POST UP | Health check vẫn critical, ứng dụng chưa ready hoặc endpoint mạng lỗi | Kiểm tra health, readiness, network và registry check |

Khi điều tra, hãy kiểm tra theo chuỗi: response của Actuator, trạng thái trong registry, danh sách instance consumer nhận được và request thực tế có còn tới instance hay không. Bốn quan sát này giúp xác định lỗi nằm ở endpoint quản trị, provider, cache discovery hay tầng gọi dịch vụ.

## 11. Kết luận

Actuator serviceregistry là giao diện quản trị trạng thái registration hiện tại thông qua ServiceRegistry abstraction của Spring Cloud Commons. GET giúp đọc trạng thái; POST với JSON chứa trường status yêu cầu provider cập nhật trạng thái. Giá trị hợp lệ và ý nghĩa của chúng phụ thuộc registry, vì vậy không thể giả định Eureka, Consul và ZooKeeper có cùng quy ước.

Trong bảo trì có kế hoạch, hãy đọc trạng thái, chuyển instance sang trạng thái không phục vụ, xác minh registry và consumer đã cập nhật, drain request rồi mới dừng tiến trình. Sau bảo trì, khôi phục trạng thái, kiểm tra health và xác nhận instance đã trở lại luồng discovery. Bảo vệ endpoint quản trị bằng phân quyền, TLS và audit log để tránh thay đổi trạng thái ngoài ý muốn.

## Tài liệu tham khảo

- [Spring Cloud Commons — ServiceRegistry và Service Registry Actuator Endpoint](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Netflix — Eureka Health Checks và Pause/Resume](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Consul — Service Discovery và Health Check](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Zookeeper — Service Registry và Instance Status](https://docs.spring.io/spring-cloud-zookeeper/reference/service-registry.html)
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)


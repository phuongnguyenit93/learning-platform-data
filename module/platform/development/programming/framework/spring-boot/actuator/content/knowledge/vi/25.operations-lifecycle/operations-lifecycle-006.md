# Bật endpoint shutdown có chủ đích và kiểm tra giới hạn hỗ trợ

`shutdown` là thao tác quản trị dùng để yêu cầu Spring Boot đóng ngữ cảnh ứng dụng (`ApplicationContext`) của bản chạy nhận yêu cầu. Với cấu hình đường dẫn mặc định, thao tác qua HTTP là `POST /actuator/shutdown` và không cần nội dung gửi kèm. Đóng ngữ cảnh sẽ kích hoạt vòng đời dừng của Spring, gồm dừng máy chủ nhúng và hủy các bean theo cơ chế vòng đời tương ứng. Do thao tác làm gián đoạn phục vụ, Spring Boot 3.3 tắt endpoint này mặc định. [API shutdown](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/shutdown.html) · [ShutdownEndpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/context/ShutdownEndpoint.html)

## Kiểm tra phiên bản, kiểu đóng gói và quyền truy cập

1. **Kiểm tra kiểu triển khai.** Spring Boot 3.3 ghi nhận hỗ trợ `shutdown` với kiểu đóng gói JAR. Trường hợp điển hình là JAR thực thi chạy với máy chủ nhúng. Với WAR triển khai vào servlet container bên ngoài, hãy dùng cơ chế dừng hoặc gỡ triển khai của container hoặc nền tảng quản lý nó. Việc thấy một đường dẫn được ánh xạ chưa đủ để xác nhận kiểu triển khai đó nằm trong phạm vi hỗ trợ. [Danh sách endpoint của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
2. **Bật endpoint và công bố qua HTTP.** Trong Spring Boot 3.3, `management.endpoint.shutdown.enabled=true` bật endpoint. Thêm `shutdown` vào `management.endpoints.web.exposure.include` để có thể gọi qua HTTP. Nếu danh sách `exclude` cũng có `shutdown`, cấu hình loại trừ được ưu tiên. Kiểm tra cấu hình thực tế của hồ sơ đang hoạt động (profile) và mọi giá trị ghi đè lúc khởi chạy. [Bật và công bố endpoint trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
3. **Dùng thuộc tính đúng phiên bản.** Tài liệu Spring Boot 3.4 dùng `management.endpoint.shutdown.access=unrestricted` để cho phép thao tác ghi của endpoint. Trần toàn cục `management.endpoints.access.max-permitted=read-only` vẫn chặn thao tác ghi. Thuộc tính `access` điều khiển các thao tác Actuator được phép, còn việc công bố qua HTTP và quyền của người gọi do các lớp cấu hình riêng quyết định. [Quyền truy cập endpoint trong Spring Boot 3.4](https://docs.spring.io/spring-boot/3.4/reference/actuator/endpoints.html)
4. **Giới hạn người gọi.** Trong môi trường dùng chung, chỉ cho phép chủ thể vận hành đã xác thực và được cấp quyền gọi thao tác dừng. Có thể giới hạn cổng quản trị bằng mạng nội bộ và áp dụng kiểm soát truy cập cho tuyến quản trị. Khi dùng Spring Security, `POST` còn chịu quy tắc CSRF của chuỗi bảo mật đang áp dụng. Kiểm tra quyền và mã CSRF phù hợp trước khi thay đổi chính sách bảo mật. [Bảo mật endpoint Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security)

## Thử trên một JAR cục bộ

Chuẩn bị một JAR thực thi Spring Boot 3.3 dùng `spring-boot-starter-web` và `spring-boot-starter-actuator`. Bài thử giả định ứng dụng mẫu dùng đường dẫn quản trị mặc định, cùng cổng với ứng dụng, và không có Spring Security. Đặt tên bản sao JAR dùng để thử là `shutdown-demo.jar`. Trong cùng thư mục, tạo `application-shutdown-lab.properties`.

```properties
server.address=127.0.0.1
server.port=8080
management.endpoint.shutdown.enabled=true
management.endpoints.web.exposure.include=health,shutdown
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

`server.shutdown=graceful` bật chế độ dừng có thời gian chờ của máy chủ nhúng trong Spring Boot 3.3. Khi ngữ cảnh đóng, máy chủ cho các yêu cầu đang xử lý thời gian hoàn tất trong giới hạn cấu hình. Giá trị `20s` ở đây là giới hạn cho từng giai đoạn dừng của vòng đời Spring. Cấu hình này điều khiển **cách** máy chủ dừng, còn cấu hình Actuator điều khiển **cách gửi yêu cầu dừng**. [Graceful shutdown trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)

Chạy ứng dụng và đợi máy chủ khởi động.

```bash
java -jar ./shutdown-demo.jar --spring.profiles.active=shutdown-lab
```

Từ terminal thứ hai, kiểm tra máy chủ rồi gửi đúng một yêu cầu dừng. Trong PowerShell trên Windows, dùng `curl.exe`.

```bash
curl -i http://127.0.0.1:8080/actuator/health
curl -i -X POST http://127.0.0.1:8080/actuator/shutdown
```

Yêu cầu thứ hai trả về `200 OK` và nội dung dạng sau.

```json
{"message":"Shutting down, bye..."}
```

Phản hồi xác nhận yêu cầu đã khởi động quá trình dừng. Để xác nhận dừng hoàn tất, quan sát nhật ký đóng ngữ cảnh hoặc việc máy chủ ngừng trả lời sau khi kết thúc giai đoạn chờ. Với JAR mẫu, có thể kiểm tra thêm việc lệnh `java -jar` đã kết thúc trong terminal đầu tiên. Trong hệ thống có nhiều bản chạy, hãy kiểm tra đúng bản chạy nhận yêu cầu và xem bộ quản lý tiến trình có khởi động lại nó hay không.

## Đọc kết quả khi kiểm tra giới hạn

| Kết quả trong bài thử | Điều cần kiểm tra |
| --- | --- |
| `POST` trả `404` trong khi `/actuator/health` vẫn trả `200` | Kiểm tra đường dẫn quản trị và cấu hình bật, công bố endpoint. Thử chạy lại với `--management.endpoint.shutdown.enabled=false` hoặc `--management.endpoints.web.exposure.exclude=shutdown`, mỗi lần một thuộc tính. Cả hai trường hợp đều cho `404` ở ứng dụng mẫu và ứng dụng vẫn chạy. |
| `GET /actuator/shutdown` trả `405` khi tuyến đã được ánh xạ | Dùng `POST` cho thao tác ghi. Có thể dùng `GET /actuator` để kiểm tra liên kết khám phá nếu tính năng đó đang bật. |
| `POST` trả `401` hoặc `403` ở môi trường có bảo mật | Kiểm tra thông tin xác thực, quyền thực hiện thao tác và chính sách CSRF. Việc mở endpoint qua HTTP chỉ làm tuyến có thể được ánh xạ. |
| Kết nối thất bại | Kiểm tra tiến trình còn chạy, địa chỉ lắng nghe và cổng quản trị. Nếu dùng `management.server.port`, gửi yêu cầu đến cổng quản trị đã đặt. |

Nếu tùy chỉnh `management.endpoints.web.base-path`, hãy dùng tiền tố đã đặt thay cho `/actuator`. Proxy hay chuỗi bảo mật cũng có thể trả phản hồi trước khi yêu cầu đến Actuator. [Đường dẫn và cổng quản trị](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)

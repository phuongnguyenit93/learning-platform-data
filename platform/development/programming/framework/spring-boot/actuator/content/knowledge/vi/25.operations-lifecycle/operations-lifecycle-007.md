# Phân biệt gọi shutdown endpoint với cấu hình graceful shutdown của web server

Khi cần dừng một phiên bản Spring Boot đang phục vụ yêu cầu, có hai quyết định riêng. **Tín hiệu nào bắt đầu đóng ứng dụng?** Và **máy chủ web xử lý các yêu cầu đang chạy thế nào trong lúc đóng?** Endpoint `shutdown` là một cách gửi tín hiệu. `server.shutdown` chọn cách máy chủ web nhúng dừng sau khi ứng dụng bắt đầu đóng.

Các thuộc tính và ví dụ trong bài dùng Spring Boot **3.3.x**.

## Endpoint shutdown khởi động việc đóng ứng dụng

Với Actuator, `POST /actuator/shutdown` yêu cầu đóng `ApplicationContext`. Spring Boot 3.3 tắt endpoint này theo mặc định. Để gọi qua HTTP, endpoint phải được bật và đưa vào danh sách endpoint được mở qua web.

```properties
management.endpoint.shutdown.enabled=true
management.endpoints.web.exposure.include=health,shutdown
```

Đường dẫn `/actuator/shutdown` giả định dùng đường dẫn gốc Actuator mặc định. Nếu ứng dụng có cổng quản trị riêng, hãy gửi yêu cầu đến cổng đó. Trong môi trường triển khai, hãy giới hạn quyền gọi endpoint cho hệ thống vận hành được phép vì đây là thao tác dừng phiên bản ứng dụng. Với Spring Security, yêu cầu `POST` còn có thể bị từ chối bởi kiểm tra CSRF tùy cấu hình.

Phản hồi thành công là HTTP 200 với trường `message` mang giá trị `Shutting down, bye...` trong cấu hình mặc định của ví dụ. Endpoint khởi động việc đóng trên luồng khác. Vì vậy, mã 200 báo thao tác đã được tiếp nhận, còn việc chờ yêu cầu đang chạy và đóng tài nguyên diễn ra sau đó. Muốn xác nhận ứng dụng đã dừng, hãy xem tiến trình hoặc nhật ký hoàn tất dừng.

## Graceful shutdown chi phối cách máy chủ web dừng

Cấu hình sau yêu cầu máy chủ web nhúng ngừng nhận yêu cầu mới và cho các yêu cầu đang xử lý thời gian hoàn tất khi ngữ cảnh ứng dụng đóng.

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=15s
```

`spring.lifecycle.timeout-per-shutdown-phase` là thời gian chờ **cho mỗi pha dừng** các thành phần vòng đời, trong đó có pha dừng máy chủ web. Tổng thời gian đóng ứng dụng còn phụ thuộc các pha khác. Một yêu cầu kéo dài hơn thời gian chờ có thể bị ngắt khi máy chủ tiếp tục dừng. Khi dùng `server.shutdown=immediate`, máy chủ bỏ qua khoảng chờ dành cho yêu cầu đang chạy.

Cách từ chối yêu cầu mới tùy máy chủ. Với Spring Boot 3.3, Tomcat, Jetty và Reactor Netty ngừng nhận yêu cầu mới ở tầng mạng. Undertow có thể nhận kết nối và trả HTTP 503. Kết quả quan sát từ máy khách còn phụ thuộc kết nối được tái sử dụng và lớp trung gian. Hãy kiểm tra đúng máy chủ mà ứng dụng đang chạy khi diễn giải mã lỗi.

| Tình huống | Tác nhân bắt đầu dừng | Xử lý yêu cầu đang chạy |
| --- | --- | --- |
| Endpoint mở, `server.shutdown=immediate` | Gửi `POST` đến Actuator | Có thể bị ngắt khi máy chủ dừng. |
| Endpoint mở, `server.shutdown=graceful` | Gửi cùng yêu cầu `POST` | Có thời gian hoàn tất trong pha dừng web. |
| Endpoint tắt, `server.shutdown=graceful` | Một tác nhân khác đóng ngữ cảnh, ví dụ `SIGTERM` trên Unix với shutdown hook của JVM hoạt động | Vẫn có thời gian hoàn tất trong pha dừng web. |
| Đã đặt `server.shutdown=graceful` và ứng dụng vẫn chạy bình thường | Chưa có tác nhân đóng ngữ cảnh | Máy chủ tiếp tục phục vụ như bình thường. |

Khi hệ điều hành kết thúc tiến trình cưỡng bức, chẳng hạn `SIGKILL` trên Unix, JVM không chạy được shutdown hook. Trong triển khai, thời hạn dừng do nền tảng cấp cần đủ cho các pha đóng ứng dụng. Để giảm yêu cầu mới đi vào phiên bản sắp dừng, tầng định tuyến cũng cần ngừng chuyển lưu lượng tới phiên bản đó.

## Thực hành với Spring Boot 3.3 và Tomcat nhúng

Ví dụ chạy trên địa chỉ loopback. Endpoint `GET /slow` mất khoảng tám giây để phản hồi, đủ để quan sát một yêu cầu đang chạy tại thời điểm gửi lệnh dừng. Lưu mã vào `ShutdownDemo.java`.

```java
package demo.shutdown;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ShutdownDemo {
    public static void main(String[] args) {
        SpringApplication.run(ShutdownDemo.class, args);
    }

    @GetMapping("/slow")
    public String slow() throws InterruptedException {
        System.out.println("WORK_STARTED");
        Thread.sleep(8_000);
        System.out.println("WORK_FINISHED");
        return "work completed";
    }
}
```

Đặt `pom.xml` sau cạnh tệp Java. `spring-boot-starter-web` cung cấp Tomcat nhúng và `spring-boot-starter-actuator` cung cấp endpoint quản trị.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo.shutdown</groupId>
    <artifactId>shutdown-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
            <version>3.3.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
            <version>3.3.0</version>
        </dependency>
    </dependencies>
</project>
```

Dùng Maven để tải thư viện và JDK 17 trở lên để biên dịch. Chạy ứng dụng trong cửa sổ thứ nhất, với cổng local `18089` đang rảnh.

```bash
mvn -q dependency:copy-dependencies -DincludeScope=runtime -DoutputDirectory=lib
javac -cp "lib/*" -d out ShutdownDemo.java
java -cp "out:lib/*" demo.shutdown.ShutdownDemo --server.address=127.0.0.1 --server.port=18089 --management.endpoint.shutdown.enabled=true --management.endpoints.web.exposure.include=health,shutdown --server.shutdown=graceful --spring.lifecycle.timeout-per-shutdown-phase=15s
```

Trên Windows, đổi classpath khi chạy thành `"out;lib/*"` và dùng `curl.exe` nếu PowerShell ánh xạ `curl` sang lệnh khác.

1. Trong cửa sổ thứ hai, bắt đầu yêu cầu chậm.

   ```bash
   curl -sS -w "\nHTTP %{http_code}\n" http://127.0.0.1:18089/slow
   ```

2. Khi cửa sổ ứng dụng in `WORK_STARTED`, lập tức gửi lệnh sau từ cửa sổ thứ ba, trước khi `WORK_FINISHED` xuất hiện.

   ```bash
   curl -sS -w "\nHTTP %{http_code}\n" -X POST http://127.0.0.1:18089/actuator/shutdown
   ```

3. Với thời gian chờ 15 giây, lệnh dừng trả HTTP 200 và yêu cầu `GET /slow` đang chạy hoàn tất. Hai dòng do chính đoạn Java in ra, xen giữa nhật ký Spring Boot, là:

   ```text
   WORK_STARTED
   WORK_FINISHED
   ```

   Cửa sổ gọi `GET /slow` nhận:

   ```text
   work completed
   HTTP 200
   ```

4. Khởi động lại bằng cùng lệnh `java`, chỉ đổi thành `--server.shutdown=immediate`, rồi lặp lại. Lệnh `POST` vẫn có thể trả HTTP 200, trong khi yêu cầu chậm đang chạy bị ngắt. Sau đó thử `graceful` với `--spring.lifecycle.timeout-per-shutdown-phase=1s`. Nếu lệnh dừng đến khi yêu cầu còn hơn một giây xử lý, thời gian chờ sẽ hết trước khi yêu cầu hoàn tất. Thông báo lỗi cụ thể ở máy khách phụ thuộc vào cách kết nối đóng.

Nếu lệnh `POST` trả 404, hãy kiểm tra việc bật endpoint, danh sách mở qua web, cổng và đường dẫn quản trị. Nếu trả 401 hoặc 403, kiểm tra thông tin xác thực, quyền gọi và cấu hình CSRF tương ứng. Nếu lệnh `POST` thành công nhưng yêu cầu đang chạy bị ngắt, hãy kiểm tra chế độ dừng, thời gian chờ theo pha và việc nền tảng có kết thúc tiến trình trước hạn hay không.

Tài liệu Spring Boot 3.3. [REST API của endpoint shutdown](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/shutdown.html) · [Bật và mở endpoint Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html) · [Graceful shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)

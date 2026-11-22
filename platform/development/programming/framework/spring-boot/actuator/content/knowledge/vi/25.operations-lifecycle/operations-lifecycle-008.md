# Phối hợp ngừng nhận yêu cầu, hoàn tất yêu cầu đang xử lý và timeout tắt

Một máy chủ đang ghi đơn hàng có thể nhận lệnh dừng ngay giữa lần ghi. Nếu tiến trình biến mất ngay, phía gọi có thể mất phản hồi dù dữ liệu đã được lưu. Nếu tiếp tục chuyển yêu cầu mới đến máy chủ đang dừng, lượng việc cần hoàn tất lại tăng. **Tắt có kiểm soát (graceful shutdown)** phối hợp ba việc: ngừng giao việc mới, cho việc đã nhận thời gian hoàn tất, rồi giải phóng tài nguyên theo một giới hạn đã định.

## Mỗi lớp thực hiện một phần

| Lớp | Việc cần phối hợp | Tín hiệu quan sát |
| --- | --- | --- |
| Bộ định tuyến hoặc cân bằng tải | Ngừng chọn phiên bản ứng dụng đang rút khỏi phục vụ. | Trạng thái backend, readiness probe, EndpointSlice và log định tuyến. |
| Spring Boot và máy chủ HTTP | Chuyển readiness sang `REFUSING_TRAFFIC` khi bắt đầu tắt, ngừng nhận yêu cầu HTTP mới theo cơ chế của máy chủ và chờ yêu cầu đang xử lý. | Sự kiện `AvailabilityChangeEvent`, log bắt đầu/kết thúc shutdown, kết quả phía gọi HTTP. |
| Mã ứng dụng và các tài nguyên nền | Ngừng lấy thêm việc, hoàn tất hoặc bàn giao việc còn lại, đóng tài nguyên theo thứ tự phụ thuộc. | Số việc đang chạy, lần xác nhận thông điệp cuối, log đóng executor và pool kết nối. |
| Môi trường triển khai | Gửi tín hiệu dừng và dành đủ thời gian trước khi buộc tiến trình thoát. | Mốc nhận tín hiệu, thời gian thoát, mã hoặc lý do kết thúc tiến trình. |

Readiness diễn đạt **phiên bản này còn nên nhận lưu lượng hay không**. Khi Actuator còn trả lời, `/actuator/health/readiness` cung cấp trạng thái cho bộ điều phối. Khi máy chủ hoặc cổng probe đã đóng, probe có thể lỗi kết nối thay vì trả một phản hồi `503`. Trong giai đoạn ứng dụng còn xử lý nốt yêu cầu, liveness vẫn có thể là `CORRECT`. Việc rút ứng dụng khỏi luồng định tuyến cần thời gian lan truyền, nên readiness và khả năng từ chối ở máy chủ hỗ trợ nhau.

## Spring Boot 3.3 tắt ứng dụng như thế nào?

1. **Kích hoạt đường đóng bình thường.** Khi JVM xử lý `SIGTERM` và shutdown hook mặc định còn hoạt động, Spring Boot đóng `ApplicationContext`. Với container Linux, cấu hình lệnh khởi chạy để tín hiệu tới được JVM, ví dụ dùng dạng exec trong `ENTRYPOINT` hoặc `exec java …` ở cuối script. `SIGKILL` kết thúc tiến trình ngay, bỏ qua đường đóng này.
2. **Chặn yêu cầu mới và xử lý nốt.** Trên dòng 3.3, bật `server.shutdown=graceful` để dùng giai đoạn chờ, vì mặc định là `immediate`. Việc chờ của máy chủ web diễn ra trong giai đoạn dừng `SmartLifecycle` sớm nhất. Tomcat, Jetty và Reactor Netty ngừng nhận ở lớp mạng. Undertow có thể vẫn nhận kết nối và trả `503` ngay. Kết nối giữ lâu, proxy và việc dùng lại kết nối có thể làm biểu hiện phía gọi khác nhau.
3. **Chuyển sang các giai đoạn còn lại.** `spring.lifecycle.timeout-per-shutdown-phase` đặt thời gian chờ cho **mỗi nhóm `SmartLifecycle` cùng phase**. Khi máy chủ đã xử lý hết yêu cầu, bước chờ có thể kết thúc sớm. Khi hết thời gian, Spring tiếp tục quá trình tắt và yêu cầu còn chạy có thể mất kết nối trước khi trả kết quả. Tổng thời gian đóng còn gồm các phase khác, callback hủy bean và phần dọn dẹp của máy chủ hoặc JVM. Thuộc tính này là giới hạn chờ của từng phase. Một phương thức dừng đồng bộ tự chặn hoặc một callback hủy bean chậm vẫn có thể kéo dài thời gian đóng.

Các thành phần `SmartLifecycle` thường dừng theo phase từ cao xuống thấp, có xét quan hệ phụ thuộc. Với thành phần tự triển khai `stop(Runnable)`, gọi callback khi việc dừng thực sự hoàn tất để bộ điều phối vòng đời biết lúc nào có thể đi tiếp. Giữ kết nối cơ sở dữ liệu hoặc HTTP client còn dùng được tới khi các tác vụ cần chúng đã hoàn tất. Các luồng xử lý ngoài HTTP như consumer, lịch chạy định kỳ và công việc đã chuyển sang executor cần chính sách riêng để dừng nhận, chờ có giới hạn và xử lý phần việc còn lại.

## Thí nghiệm Actuator với một yêu cầu chạy tám giây

Dùng JDK 17+ và Gradle tương thích. Tạo dự án riêng với ba tệp dưới đây. Ví dụ dùng đầu nối Tomcat NIO2 để chạy với cùng cấu hình máy chủ như lần kiểm chứng. Endpoint `shutdown` được mở cho thí nghiệm cục bộ trên `127.0.0.1` và chủ động đóng context. Phản hồi của lệnh POST xác nhận lệnh dừng đã được tiếp nhận. Tiến trình thoát và kết quả của yêu cầu đang chạy được kiểm tra riêng.

Tệp `build.gradle`

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

application {
    mainClass = 'demo.ShutdownDemo'
}
```

Tệp `src/main/resources/application.properties`

```properties
server.address=127.0.0.1
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=15s
management.endpoint.health.probes.enabled=true
management.endpoint.shutdown.enabled=true
management.endpoints.web.exposure.include=health,shutdown
```

Tệp `src/main/java/demo/ShutdownDemo.java`

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ShutdownDemo {

    public static void main(String[] args) {
        SpringApplication.run(ShutdownDemo.class, args);
    }

    @Bean
    WebServerFactoryCustomizer<TomcatServletWebServerFactory> useNio2() {
        return factory -> factory.setProtocol("org.apache.coyote.http11.Http11Nio2Protocol");
    }

    @GetMapping("/work")
    public String work() throws InterruptedException {
        System.out.println("WORK_START");
        Thread.sleep(8000);
        System.out.println("WORK_FINISH");
        return "done";
    }

    @EventListener
    public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println("READINESS " + event.getState());
    }
}
```

1. Ở terminal A, chạy `gradle run` và đợi dòng `READINESS ACCEPTING_TRAFFIC`. Có thể kiểm tra readiness bằng `curl -i http://127.0.0.1:8080/actuator/health/readiness`. Với ví dụ này, phản hồi khi sẵn sàng là `200` và `{"status":"UP"}`.
2. Ở terminal B, chạy lệnh dưới đây. `WORK_START` ở terminal A xác nhận yêu cầu đã vào phương thức xử lý. `Thread.sleep` mô phỏng một tác vụ có thời lượng xác định.

   ```bash
   curl -i --max-time 20 http://127.0.0.1:8080/work
   ```

3. Ngay khi thấy `WORK_START`, ở terminal C gọi lệnh dừng. Các lệnh dùng `curl.exe` nếu chạy trên Windows PowerShell.

   ```bash
   curl -i -X POST http://127.0.0.1:8080/actuator/shutdown
   ```

   Khi terminal A báo bắt đầu graceful shutdown, thử mở kết nối HTTP mới tới readiness.

   ```bash
   curl -i --max-time 2 http://127.0.0.1:8080/actuator/health/readiness
   ```

4. Đợi tiến trình thoát. Lặp lại với `gradle run --args="--spring.lifecycle.timeout-per-shutdown-phase=2s"`, giữ nguyên yêu cầu tám giây. Gửi lệnh dừng sớm sau `WORK_START` để tại lúc bắt đầu tắt, yêu cầu còn hơn hai giây xử lý.

Kết quả đo trên Java 17, Spring Boot 3.3.0 và Tomcat NIO2:

| Thời gian chờ của phase | Yêu cầu tám giây đã được nhận | Kết nối HTTP mới sau khi bắt đầu tắt |
| --- | --- | --- |
| 15 giây | Có `WORK_FINISH`, phía gọi nhận `HTTP/1.1 200` với nội dung `done`. Sau đó log báo tắt có kiểm soát hoàn tất. | curl ghi `000`, tức lần thử không nhận được mã trạng thái HTTP. |
| 2 giây | Log báo `webServerGracefulShutdown` vẫn chạy khi phase hết 2.000 ms. curl báo `(52) Empty reply from server`. | curl cũng ghi `000`. |

Cả hai lần đều ghi `READINESS REFUSING_TRAFFIC` sau `WORK_START` và trước thông báo máy chủ bắt đầu chờ. Lần 15 giây hoàn tất việc chờ sau khoảng 7,46 giây kể từ khi máy chủ bắt đầu tắt. Lần 2 giây đi tiếp khi vẫn còn yêu cầu đang xử lý.

Thứ tự quan sát có giá trị hơn một mã lỗi cố định: yêu cầu thứ nhất đã vào ứng dụng, máy chủ bắt đầu đóng, rồi yêu cầu thứ nhất hoàn tất hoặc bị gián đoạn tùy thời gian còn lại. Phản hồi cụ thể của kết nối mới có thể thay đổi theo thời điểm gửi, máy chủ và lớp trung gian. Nếu phép thử gửi yêu cầu mới trước khi máy chủ bắt đầu chặn, kết quả chỉ phản ánh khoảng chuyển tiếp.

## Ghép các giới hạn thời gian khi triển khai

Tách ba đồng hồ khi chọn cấu hình:

- **Giới hạn của yêu cầu** gồm thời gian chờ ở phía gọi, proxy và phụ thuộc phía sau. Nếu proxy chỉ chờ 10 giây, máy chủ cho 20 giây để tắt vẫn có thể hoàn thành công việc sau khi phía gọi đã mất kết nối. Chọn thời gian dựa trên loại yêu cầu thật, bao gồm truy vấn chậm, truyền dữ liệu và thử lại ở dịch vụ phụ thuộc.
- **Thời gian chờ bên trong ứng dụng** cần đủ cho phần công việc còn lại của yêu cầu đã nhận và các bước dừng có thứ tự. Với công việc dài hoặc luồng truyền liên tục như SSE, thiết kế điểm kết thúc, cơ chế kết nối lại hoặc cách khôi phục. Với thao tác ghi, phản hồi bị mất có thể khiến phía gọi không biết giao dịch đã thành công hay chưa. Khóa chống xử lý lặp (idempotency key) hoặc quy trình kiểm tra kết quả giúp phía gọi thử lại an toàn.
- **Thời gian môi trường cấp cho tiến trình** cần bao được `preStop` nếu có, phần dừng và dọn dẹp đo được của JVM, cùng khoảng dự phòng. Ví dụ, nếu cần tối đa 5 giây để bộ định tuyến ngừng chuyển lưu lượng trong bước chuẩn bị, dự trù 20 giây cho yêu cầu đang xử lý, 8 giây cho các bước đóng khác và 7 giây dự phòng thì ngân sách ví dụ là 40 giây. Xác nhận các con số bằng lần triển khai thử với tải thật.

Trên Kubernetes, bộ đếm `terminationGracePeriodSeconds` bắt đầu trước `preStop`. Khi Pod đi vào trạng thái đang kết thúc, việc cập nhật EndpointSlice diễn ra song song với các bước dừng cục bộ, nên thứ tự mà proxy quan sát có thể khác thứ tự log trong ứng dụng. Trong luồng thông thường, kubelet thực thi `preStop` nếu có, yêu cầu gửi tín hiệu dừng tới tiến trình chính, rồi có thể buộc dừng khi hết thời gian. Việc ứng dụng mất kết nối probe sau khi bắt đầu tắt là một dấu hiệu cần đọc cùng trạng thái định tuyến và log, vì probe chỉ phản ánh đường HTTP mà nó truy cập.

## Kiểm tra khi thay phiên bản dưới tải

1. Gửi một yêu cầu ngắn, một yêu cầu dài và một yêu cầu mới sau khi bắt đầu dừng. Thử cả đi thẳng tới máy chủ và qua bộ cân bằng tải để tách hai lớp.
2. Đối chiếu mốc bắt đầu rút backend, readiness, mốc bắt đầu tắt, phản hồi cuối cùng và lúc tiến trình thoát. Kiểm tra số yêu cầu đã nhận bị ngắt, số lỗi kết nối hoặc `5xx` và số lần bị buộc dừng.
3. Lặp lại với ngân sách thiếu, phụ thuộc phản hồi chậm hoặc công việc nền chưa hoàn tất. Xác minh việc ghi dữ liệu, xác nhận thông điệp và hành vi thử lại từ phía gọi. Một lần tắt nhanh có thể đến từ việc bỏ dở công việc, nên đo cả thời gian thoát lẫn kết quả của từng loại công việc.

## Tài liệu đối chiếu

- [Spring Boot 3.3 · Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)
- [Spring Boot 3.3 · Actuator shutdown](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/shutdown.html)
- [Spring Boot 3.3 · Endpoints và trạng thái probe](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Spring Framework 6.1 · SmartLifecycle](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/context/SmartLifecycle.html)
- [Kubernetes · Vòng đời Pod và trình tự kết thúc](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)
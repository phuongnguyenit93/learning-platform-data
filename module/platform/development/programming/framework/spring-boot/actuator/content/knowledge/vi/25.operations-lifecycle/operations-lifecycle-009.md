# Kiểm tra readiness và dữ liệu quan sát khi ứng dụng dừng

Khi dừng một bản chạy đang phục vụ, cần kiểm tra hai việc riêng biệt: ứng dụng đã báo rằng nó không còn sẵn sàng nhận lưu lượng hay chưa, và các yêu cầu đã được nhận có hoàn tất trong thời gian chờ hay không. Một lần gọi health thành công hoặc một dòng log riêng lẻ chỉ trả lời được một phần.

## Phân biệt trạng thái trong ứng dụng và kết quả probe

Spring Boot giữ trạng thái sẵn sàng trong `ApplicationAvailability`. Readiness cho biết bản chạy có sẵn sàng nhận lưu lượng hay không. Liveness phản ánh ứng dụng còn hoạt động đúng theo trạng thái vòng đời của nó. Khi ngữ cảnh web bắt đầu đóng, Boot phát sự kiện `ReadinessState.REFUSING_TRAFFIC`. Trong giai đoạn dừng có thời gian chờ, liveness vẫn có thể là `CORRECT` trong lúc máy chủ xử lý nốt các yêu cầu đã nhận. [Trạng thái probe theo vòng đời Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes.lifecycle)

| Giai đoạn | Trạng thái bên trong | Dấu hiệu từ bên ngoài |
| --- | --- | --- |
| Đã khởi động và sẵn sàng | `ACCEPTING_TRAFFIC`, liveness `CORRECT` | Với nhóm readiness mặc định, `GET /actuator/health/readiness` trả `200` và `UP`. |
| Bắt đầu dừng có thời gian chờ | `REFUSING_TRAFFIC`, liveness vẫn có thể là `CORRECT` | Nếu yêu cầu probe còn đến được Actuator, chỉ báo readiness báo `OUT_OF_SERVICE`, mặc định ánh xạ sang HTTP `503`. Khi máy chủ đã chặn kết nối mới, probe cùng cổng có thể gặp lỗi kết nối hoặc hết thời gian chờ. |
| Đã dừng xong | Ngữ cảnh và máy chủ đã đóng | Không còn probe trực tiếp để đọc trạng thái từ bản chạy đó. Dựa vào nhật ký, kết quả yêu cầu đã gửi và sự kiện của nền tảng để đối chiếu. |

`REFUSING_TRAFFIC` là trạng thái trong bộ nhớ. Việc đổi trạng thái không tự chặn từng yêu cầu HTTP ở tầng ứng dụng. Trong hệ thống có cấu hình probe, kết quả kiểm tra được cập nhật theo chu kỳ. Bản chạy có thể còn nhận lưu lượng trong khoảng thời gian kết quả chưa được áp dụng vào định tuyến. Cơ chế dừng của máy chủ nhúng xử lý các kết nối trực tiếp tới bản chạy. Với Spring Boot 3.3, Tomcat, Jetty và Reactor Netty ngừng nhận yêu cầu mới ở tầng mạng trong giai đoạn dừng có thời gian chờ. Undertow có thể trả `503` ở tầng máy chủ. Một `503` do máy chủ hoặc proxy tạo ra chỉ xác nhận yêu cầu bị từ chối ở tầng đó. Để biết Actuator đã trả trạng thái readiness nào, hãy kiểm tra cả đường dẫn, nội dung phản hồi và nơi tạo phản hồi. [Graceful shutdown trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)

## Thử với một yêu cầu đang xử lý

Ví dụ dùng Java 17 trở lên, Gradle, Spring Boot 3.3 và Tomcat nhúng. Chạy trên máy cục bộ với cổng 8080 còn trống. Đặt ba tệp sau trong một thư mục thử riêng. Endpoint dừng trong ví dụ chỉ lắng nghe qua máy chủ gắn với địa chỉ loopback.

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

tasks.named('bootJar') {
    archiveFileName = 'readiness-lab.jar'
}
```

**`src/main/java/demo/readiness/ReadinessLab.java`**

```java
package demo.readiness;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.event.EventListener;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ReadinessLab {
    private static final Logger log = LoggerFactory.getLogger(ReadinessLab.class);

    public static void main(String[] args) {
        SpringApplication.run(ReadinessLab.class, args);
    }

    @EventListener
    public void onAvailability(AvailabilityChangeEvent<?> event) {
        if (event.getState() instanceof ReadinessState state) {
            log.info("readiness={}", state);
        }
    }

    @GetMapping("/slow")
    public String slow() throws InterruptedException {
        log.info("slow: started");
        Thread.sleep(8000);
        log.info("slow: finished");
        return "slow completed";
    }
}
```

**`src/main/resources/application.properties`**

```properties
server.address=127.0.0.1
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
management.endpoint.health.probes.enabled=true
management.endpoint.shutdown.enabled=true
management.endpoints.web.exposure.include=health,shutdown
```

`management.endpoint.health.probes.enabled=true` tạo các nhóm probe cả khi chạy ngoài Kubernetes. Cấu hình `server.shutdown=graceful` bật chế độ chờ các yêu cầu đang xử lý. Giá trị `20s` là giới hạn cho mỗi giai đoạn dừng của vòng đời Spring. Trong bài thử, yêu cầu `/slow` chủ động chờ 8 giây để có thời gian gửi lệnh dừng. [Cấu hình probe](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes) · [Cấu hình thời gian chờ dừng](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)

**Terminal 1.** Tạo và chạy JAR. Giữ terminal này để đọc log.

```bash
gradle bootJar
java -jar build/libs/readiness-lab.jar
```

**Terminal 2.** Khi log đã có `readiness=ACCEPTING_TRAFFIC`, chạy vòng lặp sau bằng Bash để ghi nhận kết quả probe theo thời gian. Giữ cả mã HTTP, nội dung phản hồi và lỗi do `curl` ghi ra. Bấm Ctrl+C để dừng vòng lặp sau khi ứng dụng đã thoát.

```bash
while true; do
  printf '%s ' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  curl -sS --connect-timeout 1 --max-time 2 -w ' http=%{http_code}\n' \
    http://127.0.0.1:8080/actuator/health/readiness
  sleep 0.3
done
```

**Terminal 3.** Gửi một yêu cầu cần thời gian xử lý.

```bash
curl -i --max-time 25 http://127.0.0.1:8080/slow
```

**Terminal 4.** Ngay khi Terminal 1 ghi `slow: started`, gửi yêu cầu dừng.

```bash
curl -i --max-time 5 -X POST http://127.0.0.1:8080/actuator/shutdown
```

Nếu dừng khi `/slow` vẫn đang xử lý, log của ứng dụng có các dòng thông báo sau theo thứ tự này. Timestamp, tên luồng và các dòng log của Tomcat thay đổi theo lần chạy.

```text
readiness=ACCEPTING_TRAFFIC
slow: started
readiness=REFUSING_TRAFFIC
slow: finished
```

Đối chiếu thêm ba bằng chứng:

1. Trước lệnh dừng, probe trả `{"status":"UP"}` và `http=200`. Trong lúc dừng, probe có thể chuyển thẳng từ `200` sang lỗi kết nối hoặc timeout. `http=000` là giá trị `curl` hiển thị khi chưa nhận được mã trạng thái HTTP. Nhật ký `readiness=REFUSING_TRAFFIC` xác nhận chuyển trạng thái ngay cả khi probe đã mất đường tới ứng dụng.
2. Yêu cầu `/slow` đã bắt đầu trước khi dừng và có thể hoàn tất trong thời gian chờ. Với bài thử thành công, Terminal 3 nhận `200 OK` và nội dung `slow completed`. Nếu log có `slow: finished` nhưng bên gọi bị lỗi, chỉ có bằng chứng rằng hàm xử lý đã đi đến cuối. Dùng kết quả của bên gọi để xác nhận phản hồi thực sự đã tới nơi.
3. Phản hồi `200` của lệnh dừng xác nhận Actuator đã nhận thao tác. Dùng thời điểm log dừng và việc lệnh `java -jar` kết thúc để xác nhận bản chạy đã dừng. Nếu `slow: finished` xuất hiện trước `readiness=REFUSING_TRAFFIC`, bài thử chưa tạo được yêu cầu đang xử lý đồng thời với lúc dừng. Hãy chạy lại và gửi lệnh dừng sớm hơn. [Hợp đồng HTTP của endpoint shutdown](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/shutdown.html)

## Đối chiếu dữ liệu khi vận hành

- **Gắn cùng một định danh và mốc thời gian.** Đối chiếu thời điểm nhận lệnh dừng, thời điểm chuyển readiness, lần probe cuối cùng, thời điểm bộ định tuyến ngừng gửi lưu lượng và kết quả của các yêu cầu đã bắt đầu. Dùng cùng định danh bản chạy, chẳng hạn tên Pod, và mã yêu cầu nếu có. Quy đổi timestamp về cùng múi giờ trước khi so sánh. Qua bộ cân bằng tải, `200` có thể đến từ một bản chạy khác.
- **Đo trên cả cổng phục vụ.** Nếu Actuator chạy trên cổng quản trị riêng, probe trên cổng đó chỉ xác nhận khả năng phục vụ của cổng quản trị và trạng thái nó đọc được. Có thể đặt `management.endpoint.health.probes.add-additional-paths=true` để cung cấp `/readyz` và `/livez` trên cổng chính. Khi phân tích, ghi rõ probe nào và cổng nào đã trả kết quả. [Probe và cổng quản trị riêng](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- **Lưu bằng chứng ngoài tiến trình.** Sau khi máy chủ đóng, hệ thống thu thập có thể mất khả năng đọc endpoint và bỏ lỡ mẫu đo cuối. Đối chiếu log đã gửi ra ngoài, thời điểm thu thập số liệu gần nhất, sự kiện định tuyến và lỗi phía bên gọi. Dùng số yêu cầu đang xử lý và số yêu cầu hoàn tất hoặc lỗi trong khoảng dừng để đánh giá tác động, với điều kiện các số liệu đó thực sự được hệ thống thu thập.

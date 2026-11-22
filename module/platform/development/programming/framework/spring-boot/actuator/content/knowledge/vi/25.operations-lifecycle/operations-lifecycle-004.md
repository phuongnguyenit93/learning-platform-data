# Liên hệ dữ liệu startup với bean khởi tạo chậm và phụ thuộc ngoài

Khi một phiên bản mới mất thêm vài giây mới sẵn sàng nhận lưu lượng, dòng log tổng thời gian chỉ cho biết mức chậm. Timeline của Actuator giúp khoanh vùng **bước nào giữ quá trình khởi động lại**. Ví dụ, `reportService` mất hơn một giây để xuất hiện, nhưng phần lớn thời gian đó có thể đến từ `remoteConfig` đang chờ một dịch vụ cấu hình phản hồi qua HTTP.

## Đọc timeline theo quan hệ cha–con

Trong Spring Boot 3.3, cấu hình `BufferingApplicationStartup` trên `SpringApplication` trước `run(args)` để lưu các bước được đo. Khi ứng dụng có Actuator và đã mở endpoint `startup` qua HTTP, `GET /actuator/startup` lấy ảnh chụp bộ đệm. Dùng GET để giữ dữ liệu cho các lần đọc sau. `POST /actuator/startup` rút các sự kiện đang có khỏi bộ đệm và trả về chúng.

| Trường | Cách đọc khi tìm bean chậm |
| --- | --- |
| `timeline.startTime` | Mốc bắt đầu của bản ghi, dùng để đặt các sự kiện vào cùng một trục thời gian. |
| `startTime`, `endTime`, `duration` | Khoảng thời gian trôi qua của một bước. `PT1.2S` là 1,2 giây. Khoảng này có thể gồm thời gian chạy CPU, chờ I/O và các bước lồng bên trong. |
| `startupStep.name` và `tags` | Với `spring.beans.instantiate`, tìm tag có `key=beanName` để biết bean nào đang được tạo. Tên bước do Spring phát ra có thể thay đổi giữa các phiên bản. |
| `startupStep.id` và `parentId` | Nối bước con với bước cha trong cùng lần chạy. Sắp xếp theo `startTime` khi cần nhìn thứ tự bắt đầu. |

Một bước tạo bean có thể bao trùm việc phân giải các bean phụ thuộc, gọi phương thức `@Bean`, chạy callback khởi tạo như `@PostConstruct` và xử lý qua `BeanPostProcessor`. Khi bước con nằm trong bước cha, thời lượng của nó đã nằm trong khoảng thời gian của cha. Cộng cả hai sẽ đếm trùng. Nếu nhiều bước con chồng lấp, hãy xét phần hợp của các khoảng thời gian trước khi ước tính thời gian còn lại của cha. Phần còn lại vẫn chỉ là thời gian trôi qua chưa được giải thích bởi các bước con đã ghi.

`parentId` mô tả quan hệ lồng nhau của các bước đã ghi trong lần chạy đó. Một bean phụ thuộc đã có sẵn có thể được dùng lại mà chẳng xuất hiện thành bước con mới. Bộ đệm có giới hạn số bước, vì vậy khi thiếu một sự kiện dự kiến, hãy kiểm tra dung lượng, bộ lọc, việc từng gọi POST và thời điểm công việc thực sự chạy.

## Thí nghiệm với dịch vụ cấu hình HTTP cục bộ

Tạo một dự án Gradle riêng với JDK 17+, Gradle tương thích với JDK đang dùng và Python 3. Dùng cùng phiên bản ứng dụng cho cả hai lần chạy. Dịch vụ HTTP giả lập chạy ở tiến trình riêng, trả cùng dữ liệu và chỉ thay đổi thời gian chờ.

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
    mainClass = 'demo.StartupDemo'
}
```

Tệp `src/main/resources/application.properties`

```properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health,startup,metrics
```

Tệp `src/main/java/demo/StartupDemo.java`

```java
package demo;

import java.net.URI;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Lazy;
import org.springframework.core.metrics.ApplicationStartup;
import org.springframework.core.metrics.StartupStep;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@SpringBootApplication
public class StartupDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(StartupDemo.class);
        app.setApplicationStartup(new BufferingApplicationStartup(2048));
        app.run(args);
    }

    @Bean
    ReportService reportService(RemoteConfig config) {
        return new ReportService(config);
    }

    @Bean
    @Lazy
    RemoteConfig remoteConfig(ApplicationStartup startup,
            @Value("${demo.config-url:http://127.0.0.1:9090/config}") URI uri) {
        SimpleClientHttpRequestFactory transport = new SimpleClientHttpRequestFactory();
        transport.setConnectTimeout(1000);
        transport.setReadTimeout(3000);
        RestClient client = RestClient.builder().requestFactory(transport).build();

        StartupStep fetch = startup.start("demo.remote-config.fetch")
                .tag("dependency", "config-service");
        try {
            String body = client.get().uri(uri).retrieve().body(String.class);
            return new RemoteConfig(body);
        } finally {
            fetch.end();
        }
    }

    record RemoteConfig(String value) {}
    record ReportService(RemoteConfig config) {}
}
```

`remoteConfig` được đánh dấu `@Lazy` ở định nghĩa để Spring bỏ qua việc khởi tạo trước bean này. `reportService` vẫn được tạo lúc khởi động và cần ngay `RemoteConfig` qua tham số phương thức `@Bean`. Vì vậy lời gọi HTTP chạy trong lúc tạo `reportService`. Bước tự đặt tên `demo.remote-config.fetch` đo vùng gọi HTTP đồng bộ và xử lý kết quả, còn `finally` kết thúc bước kể cả khi lời gọi ném ngoại lệ. Tag dùng tên logic của dịch vụ để tránh đưa dữ liệu cấu hình hoặc thông tin xác thực vào bản ghi.

Tệp `mock_config.py`

```python
from http.server import BaseHTTPRequestHandler, HTTPServer
import sys
import time

delay_seconds = float(sys.argv[1]) / 1000


class ConfigHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/config":
            self.send_error(404)
            return
        time.sleep(delay_seconds)
        body = b"mode=standard"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


with HTTPServer(("127.0.0.1", 9090), ConfigHandler) as server:
    server.serve_forever()
```

Chạy `python mock_config.py 1200` ở terminal thứ nhất và `gradle run` ở terminal thứ hai. Cấu hình ví dụ chỉ lắng nghe trên địa chỉ vòng lặp của máy. Khi ứng dụng đã khởi động, lấy timeline và thời gian đến lúc sẵn sàng từ terminal thứ ba. Trên Windows PowerShell có thể dùng `curl.exe`.

```bash
curl --fail --silent --show-error http://127.0.0.1:8080/actuator/startup -o startup-slow.json
curl --fail --silent --show-error http://127.0.0.1:8080/actuator/metrics/application.ready.time -o ready-slow.json
```

Dừng cả hai tiến trình. Chạy lại với `python mock_config.py 0` và `gradle run`, rồi lưu hai phản hồi vào `startup-fast.json` và `ready-fast.json`. So sánh ba bước theo tên và tag trong `timeline.events`. Đọc ID cùng mốc thời gian của từng lần chạy.

Kết quả của một cặp lần chạy trên Java 17 và Spring Boot 3.3.0, dùng cùng đầu nối Tomcat NIO2 trong môi trường kiểm chứng:

| Bước hoặc chỉ số | Dịch vụ chờ 1.200 ms | Dịch vụ chờ 0 ms |
| --- | --- | --- |
| `reportService` | `PT1.294583S` | `PT0.0655701S` |
| `remoteConfig` | `PT1.2935835S` | `PT0.0635704S` |
| `demo.remote-config.fetch` | `PT1.2580593S` | `PT0.0490026S` |
| `application.ready.time` | 11,4 s | 10,314 s |

Ở lần chạy chậm, `reportService` có ID `103`, `remoteConfig` có ID `104` với `parentId=103`, còn `demo.remote-config.fetch` có ID `105` với `parentId=104`. Lời gọi HTTP kéo dài khoảng 1,258 giây trong tổng số 1,295 giây của bước tạo `reportService`. Đây là cùng một khoảng chờ được quan sát ở ba mức.

Lần chạy chậm cho thấy hai bước tạo bean dài vì cùng bao trùm một lần lấy cấu hình. Khi bỏ thời gian chờ ở dịch vụ giả lập, bước HTTP và cả hai bước tạo bean đều ngắn lại. Phần chênh lệch quan sát được có thể khác 1.200 ms do lần đầu tạo kết nối, lập lịch luồng và tải của máy. Bước HTTP đo từ phía ứng dụng nên vẫn gộp thời gian mạng, xử lý phía dịch vụ và nhận phản hồi.

## Từ một bước chậm đến nguyên nhân có thể kiểm chứng

1. **Xác định mốc chậm.** So sánh `application.started.time` với `application.ready.time` và dùng cùng điều kiện chạy giữa các mẫu. Spring Boot phát `ApplicationStartedEvent` sau khi làm mới context, rồi gọi các runner trước `ApplicationReadyEvent`. Nếu chậm chủ yếu giữa hai mốc, hãy đo các runner và tác vụ đồng bộ trong giai đoạn đó. Nếu chậm trước mốc started, ưu tiên phân tích timeline của phần khởi tạo context.
2. **Lần từ bước cha xuống bước con.** Tìm bước tạo bean dài, nối `parentId` và đọc mã bean gần thao tác nghi vấn nhất. Kiểm tra các vị trí như hàm tạo, `@Bean`, `@PostConstruct`, callback vòng đời và bộ xử lý bean. Với JDBC, hãy phân biệt thời gian đợi lấy kết nối, mở kết nối, xác thực và chạy truy vấn hoặc migration. Với HTTP, hãy kiểm tra DNS, kết nối, TLS, chờ phản hồi và các lần thử lại. Cùng một tên bean có thể bao nhiều loại chi phí.
3. **Đối chiếu bằng phép đo độc lập.** Đặt bước tự đo quanh lời gọi nghi vấn hoặc đối chiếu log, trace và dữ liệu phía dịch vụ bằng mốc thời gian và mã tương quan nếu có. Java Flight Recorder có thể bổ sung dấu vết CPU, tải lớp, GC hoặc I/O. Nếu dùng `FlightRecorderApplicationStartup` thay cho bộ đệm của ví dụ, thu sự kiện Spring qua bản ghi JFR. Nếu ứng dụng chết hoặc treo trước khi Actuator truy cập được, dùng log khởi động, bản ghi JFR khởi động cùng JVM hoặc bản chụp ngăn xếp luồng để tiếp tục điều tra.
4. **Đổi một yếu tố rồi đo lại.** Cố định cấu hình, dữ liệu, tài nguyên máy và cách khởi chạy. So sánh vài lần khởi động mới với phụ thuộc phản hồi bình thường, phản hồi chậm hoặc bị lỗi. Dự đoán trước bước nào sẽ dài thêm và mốc sẵn sàng sẽ đổi ra sao. Ví dụ trên chỉ thay đổi độ trễ của dịch vụ giả lập, qua đó kiểm tra trực tiếp giả thuyết rằng I/O kéo dài bước tạo bean.

## Chọn cách xử lý theo vai trò của phụ thuộc

- **Dữ liệu bắt buộc trước khi nhận lưu lượng.** Giữ điều kiện sẵn sàng gắn với việc đã lấy và kiểm tra được dữ liệu. Đặt giới hạn thời gian cho kết nối và thao tác, giới hạn tổng thời gian thử lại, ghi lỗi đủ để truy nguyên. Nếu khởi tạo thất bại, lựa chọn giữa dừng khởi động và giữ phiên bản ở trạng thái chưa sẵn sàng phụ thuộc vào cách hệ thống triển khai và phục hồi. Với Kubernetes, tránh ràng buộc liveness vào dịch vụ dùng chung bên ngoài vì sự cố của dịch vụ đó có thể khiến nhiều phiên bản bị khởi động lại đồng thời.
- **Dữ liệu có thể tải sau.** Khởi tạo client cục bộ trước, chuyển I/O sang tác vụ tải nền có kiểm soát khi ứng dụng có dữ liệu dự phòng hoặc chế độ phục vụ giới hạn rõ ràng. Đo thêm thời gian của yêu cầu đầu tiên và thời gian đến lúc dữ liệu thực sự dùng được. Khởi tạo lười có thể dời chi phí hoặc lỗi sang thời điểm bean được yêu cầu. Chuyển công việc sang `ApplicationRunner` vẫn giữ nó trước mốc sẵn sàng nếu runner chờ đồng bộ cho đến khi hoàn tất.
- **Xác nhận sau thay đổi.** Chụp lại timeline và mốc sẵn sàng, rồi thử cả khi phụ thuộc bình thường, chậm và lỗi. So sánh thời gian khởi động cùng hành vi phục vụ. Nếu thời gian trước readiness giảm nhưng yêu cầu đầu tiên chậm hơn tương ứng, chi phí đã chuyển sang đường xử lý yêu cầu.

## Tài liệu đối chiếu

- [Spring Boot 3.3 · Hợp đồng HTTP của endpoint startup](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html)
- [Spring Boot 3.3 · Ghi nhận quá trình khởi động](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-startup-tracking)
- [Spring Boot 3.3 · Chỉ số thời gian khởi động](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.application-startup)
- [Spring Boot 3.3 · Kiểm tra phụ thuộc ngoài qua probe](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes.external-state)
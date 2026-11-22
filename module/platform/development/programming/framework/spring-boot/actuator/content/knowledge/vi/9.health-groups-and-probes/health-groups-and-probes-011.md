# Quan sát trạng thái probe khi khởi động, ngừng nhận yêu cầu và tắt ứng dụng

## 1. Bắt đầu từ một lần triển khai lại ứng dụng

Một phiên bản ứng dụng vừa mở được cổng HTTP nhưng vẫn đang chuẩn bị dữ liệu. Một phiên bản khác đang hoàn tất yêu cầu cũ trước khi tắt. Cả hai đều có thể còn tiến trình Java chạy, nhưng không nên nhận thêm công việc từ bộ cân bằng tải.

Bài này hướng dẫn quan sát ba nguồn bằng chứng cùng lúc:

- **Trạng thái nội bộ:** ứng dụng tự công bố gì qua `ApplicationAvailability` và `AvailabilityChangeEvent`?
- **Probe qua HTTP:** đường dẫn kiểm tra trả mã HTTP và nội dung nào, hoặc chưa thể kết nối?
- **Yêu cầu nghiệp vụ:** lời gọi trực tiếp còn đến được ứng dụng không; yêu cầu đang xử lý có hoàn tất không?

Probe là phép kiểm tra để bên ngoài quyết định cách sử dụng một phiên bản ứng dụng. Tính sống (liveness) phản ánh khả năng hoạt động nội tại; mức sẵn sàng (readiness) phản ánh khả năng nhận lưu lượng. Hai câu hỏi này cần được quan sát riêng. Có thể đọc trạng thái trong mã qua `ApplicationAvailability`. [Spring Boot — Application Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability).

**Phạm vi thực hành:** Spring Boot 3.3.x, ứng dụng Servlet dùng Tomcat nhúng, Java 21, cùng một cổng cho nghiệp vụ và Actuator. Ví dụ cố định Spring Boot 3.3.0 để tái lập các bước. Không cần Kubernetes, cơ sở dữ liệu hoặc Spring Security. Không suy rộng các giá trị mặc định của bài sang mọi phiên bản Spring Boot.

Sau thực hành, người học cần giải thích được vì sao một ứng dụng có thể có liveness thành công nhưng readiness thất bại, vì sao readiness thất bại chưa chứng minh cổng nghiệp vụ đã đóng, và vì sao mất kết nối lúc tắt khác với nhận một phản hồi HTTP 503.

## 2. Đọc đúng ba lớp trạng thái

### 2.1. Trạng thái trong bộ nhớ không phải mã HTTP

Tên trạng thái ở từng lớp khác nhau:

| Lớp | Ví dụ |
| --- | --- |
| Mức sẵn sàng trong ứng dụng | `ReadinessState.REFUSING_TRAFFIC` |
| Kết quả health tương ứng | `OUT_OF_SERVICE` |
| Mã HTTP mặc định khi endpoint trả được phản hồi | `503` |

Với các indicator và ánh xạ mặc định, các cặp cần đối chiếu trong bài là:

| Trạng thái nội bộ | Health | HTTP |
| --- | --- | --- |
| `LivenessState.CORRECT` | `UP` | `200` |
| `LivenessState.BROKEN` | `DOWN` | `503` |
| `ReadinessState.ACCEPTING_TRAFFIC` | `UP` | `200` |
| `ReadinessState.REFUSING_TRAFFIC` | `OUT_OF_SERVICE` | `503` |

Các kết quả này giả định nhóm chỉ chứa indicator tương ứng, không thêm kiểm tra khác và không đổi ánh xạ HTTP. `ReadinessStateHealthIndicator` đọc mức sẵn sàng, còn `HttpCodeStatusMapper` đảm nhiệm lớp mã HTTP. [ReadinessStateHealthIndicator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/availability/ReadinessStateHealthIndicator.html), [SimpleHttpCodeStatusMapper](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleHttpCodeStatusMapper.html).

### 2.2. Không kết nối được thì chưa có phản hồi health

Có hai quan sát khác nhau:

```text
HTTP 503
{"status":"OUT_OF_SERVICE"}
```

và:

```text
curl: không thiết lập được kết nối
HTTP 000
```

Đoạn thứ hai mô tả tình huống lỗi kết nối; câu thông báo thực tế phụ thuộc hệ điều hành và curl. `000` là giá trị curl hiển thị khi chưa nhận được mã HTTP, không phải mã do Spring Boot trả về.

Một lần timeout cũng chưa đủ để kết luận ứng dụng đã chuyển sang `BROKEN`. Cần đối chiếu thời điểm, log vòng đời, cổng đang gọi và tình trạng tiến trình.

### 2.3. Readiness là tín hiệu cho bên định tuyến

Trong ví dụ phía dưới, `/demo/drain` chỉ phát một sự kiện đổi readiness. Phương thức đó không đóng connector và không cài bộ lọc để từ chối tất cả endpoint.

Vì vậy, ta chủ động kiểm tra hai điều sau trong cùng giai đoạn:

1. Probe readiness trả `503`.
2. Một lời gọi trực tiếp đến `/demo/work` vẫn có thể hoàn tất.

Một bộ cân bằng tải có tích hợp readiness sẽ dùng tín hiệu kiểm tra để quyết định ngừng định tuyến. Với một lời gọi curl trực tiếp tới `127.0.0.1`, không có bộ cân bằng tải thực hiện quyết định đó thay người gọi.

## 3. Những mốc cần quan sát

| Mốc | Liveness nội bộ | Readiness nội bộ | Điều có thể thấy từ bên ngoài |
| --- | --- | --- | --- |
| Đang tạo ứng dụng, chưa có trạng thái thành công | `BROKEN` | `REFUSING_TRAFFIC` | HTTP có thể chưa truy cập được |
| Ngữ cảnh đã khởi động, runner đang làm việc | `CORRECT` | `REFUSING_TRAFFIC` | Trong bài thực hành: liveness `200`, readiness `503` |
| Hoàn tất khởi động | `CORRECT` | `ACCEPTING_TRAFFIC` | Hai probe trả `200` |
| Chủ động rút khỏi luồng yêu cầu bằng `/demo/drain` | `CORRECT` | `REFUSING_TRAFFIC` | Readiness `503`; connector vẫn hoạt động |
| Cho phép nhận lưu lượng lại bằng `/demo/resume` | `CORRECT` | `ACCEPTING_TRAFFIC` | Readiness trở lại `200` |
| Đóng ngữ cảnh, thực hiện tắt có chờ | Không tự đổi thành `BROKEN` chỉ vì tắt bình thường | Chuyển sang `REFUSING_TRAFFIC` | Có thể mất khả năng gọi probe rất nhanh |
| Đã tắt xong | Không còn trạng thái để truy vấn qua ứng dụng đã tắt | Không còn trạng thái để truy vấn | Không có phản hồi HTTP từ tiến trình này |

Không coi mọi dòng là một khoảng thời gian đủ dài để curl bắt được. Mẫu lấy mỗi giây có thể bỏ qua một chuyển trạng thái chỉ tồn tại rất ngắn. Phân biệt trạng thái nội bộ với khả năng truy cập probe là yêu cầu cốt lõi khi đọc vòng đời. [Spring Boot — Application Lifecycle and Probe States](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes.lifecycle).

### 3.1. Vì sao có khoảng “đã khởi động nhưng chưa sẵn sàng”?

Với chuỗi khởi động thông thường, Spring Boot phát `ApplicationStartedEvent`, rồi công bố `LivenessState.CORRECT`. Sau khi các runner hoàn tất, nó phát `ApplicationReadyEvent`, rồi công bố `ReadinessState.ACCEPTING_TRAFFIC`. Thứ tự giữa sự kiện ứng dụng và sự kiện availability là có ý nghĩa khi viết listener. [EventPublishingRunListener, Spring Boot 3.3](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/context/event/EventPublishingRunListener.java).

Ví dụ giữ runner trong 15 giây để tạo một cửa sổ quan sát rõ ràng. Nếu chỉ nhìn thấy dòng log `Started ProbeLabApplication` rồi kết luận readiness đã thành công, người học sẽ bỏ qua công việc runner còn đang thực hiện.

Listener availability phía dưới in `event.getState()`. Không dùng một lần đọc trạng thái khác ngay trong listener để suy ra rằng mọi listener còn lại đã xử lý xong cùng sự kiện.

### 3.2. Khi bắt đầu đóng ứng dụng

Trong ngữ cảnh Servlet, đường đóng ứng dụng công bố `REFUSING_TRAFFIC` trước khi tiếp tục đóng ngữ cảnh. Mã minh họa sẽ ghi sự kiện đó và sự kiện `ContextClosedEvent` ra log. [ServletWebServerApplicationContext.doClose](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/web/servlet/context/ServletWebServerApplicationContext.java).

Tắt có chờ (graceful shutdown) cho yêu cầu đang xử lý một khoảng thời gian hoàn tất. Với Tomcat, việc ngừng nhận yêu cầu mới diễn ra ở tầng mạng; không có cam kết mọi lần gọi probe trong khoảng tắt sẽ nhận JSON 503. Undertow có cách từ chối khác. [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html).

## 4. Tạo chương trình thực hành độc lập

Tạo một thư mục riêng với cấu trúc sau:

```text
probe-lab/
  pom.xml
  src/main/java/example/probes/ProbeLabApplication.java
  src/main/resources/application.properties
```

Đây là một ứng dụng Spring Boot đầy đủ, không phải một tệp Java chỉ cần chạy bằng `javac ProbeLabApplication.java`. Maven cung cấp các thư viện và đóng gói JAR thực thi. Lần dựng đầu cần truy cập kho phụ thuộc Maven.

### 4.1. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>probe-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 4.2. Tệp application.properties

```properties
server.address=127.0.0.1
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
management.endpoints.web.exposure.include=health
management.endpoint.health.probes.enabled=true
management.endpoint.health.group.liveness.include=livenessState
management.endpoint.health.group.readiness.include=readinessState
management.endpoint.health.show-details=never
```

Cấu hình này chủ động bật probe khi chạy ngoài Kubernetes và chỉ mở endpoint health qua HTTP. Mỗi nhóm được giới hạn vào indicator trạng thái tương ứng để thí nghiệm không bị kết quả từ các kiểm tra khác chi phối. Các đường dẫn dùng trong bài là `/actuator/health/liveness` và `/actuator/health/readiness`. [Spring Boot — Kubernetes Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

`server.shutdown=graceful` làm lựa chọn tắt có chờ trở nên rõ ràng. `spring.lifecycle.timeout-per-shutdown-phase=20s` là thời hạn cho từng pha dừng vòng đời, không phải lời hứa toàn bộ quá trình tắt luôn kéo dài đúng 20 giây.

`server.address=127.0.0.1` giữ chương trình thực hành trên máy cục bộ. Các endpoint đổi trạng thái bên dưới phục vụ thí nghiệm. Không sao chép chúng thành API quản trị công khai khi triển khai ứng dụng.

### 4.3. Tệp ProbeLabApplication.java

```java
package example.probes;

import java.io.IOException;
import java.time.Instant;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ProbeLabApplication {

    public static void main(String[] args) throws IOException {
        ConfigurableApplicationContext context =
                SpringApplication.run(ProbeLabApplication.class, args);
        try {
            System.out.println("LAB: press Enter to close");
            System.in.read();
        } finally {
            context.close();
        }
    }

    @Bean
    ApplicationRunner warmup() {
        return args -> {
            System.out.println("WARMUP begin");
            Thread.sleep(15_000);
            System.out.println("WARMUP end");
        };
    }

    @EventListener
    public void availabilityChanged(AvailabilityChangeEvent<?> event) {
        Object state = event.getState();
        System.out.println(Instant.now() + " AVAIL "
                + state.getClass().getSimpleName() + "=" + state);
    }

    @EventListener
    public void contextClosed(ContextClosedEvent event) {
        System.out.println(Instant.now() + " CONTEXT closing");
    }

    @RestController
    static class LabController {

        private final ConfigurableApplicationContext context;
        private final ApplicationAvailability availability;

        LabController(ConfigurableApplicationContext context,
                ApplicationAvailability availability) {
            this.context = context;
            this.availability = availability;
        }

        @PostMapping("/demo/drain")
        String drain() {
            AvailabilityChangeEvent.publish(context,
                    ReadinessState.REFUSING_TRAFFIC);
            return availability.getReadinessState().name();
        }

        @PostMapping("/demo/resume")
        String resume() {
            AvailabilityChangeEvent.publish(context,
                    ReadinessState.ACCEPTING_TRAFFIC);
            return availability.getReadinessState().name();
        }

        @GetMapping("/demo/work")
        String work() throws InterruptedException {
            System.out.println("WORK begin");
            Thread.sleep(10_000);
            System.out.println("WORK end");
            return "completed";
        }
    }
}
```

Các điểm chủ động tạo ra trong chương trình:

- Runner đợi 15 giây để có thể gọi probe khi ứng dụng chưa hoàn tất công việc khởi động.
- `/demo/drain` và `/demo/resume` thay đổi readiness; chúng không thay đổi liveness.
- `/demo/work` xử lý trong khoảng 10 giây để quan sát một yêu cầu còn đang chạy khi đóng ứng dụng.
- Sau khi khởi động hoàn tất, luồng main chờ Enter rồi gọi `context.close()`. Cách này giúp đóng ngữ cảnh có trật tự ngay cả khi công cụ chạy không chuyển tiếp tín hiệu dừng như mong muốn.
- Các listener chỉ in thông tin, không cố giữ ngữ cảnh sống thêm để phục vụ probe.

Phép đợi trong ví dụ chỉ tạo độ trễ dễ quan sát; nó không phải công việc khởi tạo thực tế. Trong ứng dụng thật, phải gắn mức sẵn sàng với điều kiện phục vụ thực sự. Nếu công việc quan trọng được đưa sang luồng nền rồi runner trả về ngay, cửa sổ chờ runner của bài không còn đại diện cho công việc đó.

Giữ stdin của terminal mở khi chạy. Nếu chạy với stdin đã đóng, `System.in.read()` có thể nhận EOF và chương trình sẽ đóng ngữ cảnh ngay sau khởi động.

## 5. Chuẩn bị hai hoặc ba terminal

Từ thư mục `probe-lab`, dựng JAR:

```powershell
mvn -q package
```

Chạy ứng dụng ở terminal A:

```powershell
java -jar target/probe-lab-1.0.0.jar
```

Các lệnh HTTP dưới đây dùng PowerShell và `curl.exe` để tránh nhầm với alias `curl` của một số phiên bản PowerShell. Trên Linux/macOS, dùng `curl` và điều chỉnh cú pháp xuống dòng cho shell tương ứng.

Ở terminal B, chạy vòng quan sát readiness **trước khi** khởi động ứng dụng ở A, hoặc chạy ngay sau đó:

```powershell
while ($true) {
    Get-Date -Format "HH:mm:ss.fff"
    curl.exe --noproxy "*" -sS --max-time 1 -w "`nHTTP %{http_code}`n" http://127.0.0.1:8080/actuator/health/readiness
    "curl_exit=$LASTEXITCODE"
    Start-Sleep -Milliseconds 500
}
```

Vòng lặp chạy cho đến khi nhấn Ctrl+C tại **terminal B**. Nó chỉ kết thúc quá trình quan sát. Muốn đóng ứng dụng bằng cách của bài, nhấn Enter ở **terminal A** khi thấy thông báo `LAB: press Enter to close`.

`--max-time 1` giới hạn thời gian một mẫu HTTP. Đây không phải thời hạn tắt ứng dụng. Khi không nhận được HTTP, giữ lại cả lỗi curl và mã thoát để phân biệt với phản hồi `503`.

## 6. Thí nghiệm 1 — Bắt được khoảng khởi động chưa sẵn sàng

Khi terminal A đã in `WARMUP begin` nhưng chưa in `WARMUP end`, gọi nhanh từ terminal khác:

```powershell
curl.exe --noproxy "*" -sS --max-time 2 -w "`nHTTP %{http_code}`n" http://127.0.0.1:8080/actuator/health/liveness
curl.exe --noproxy "*" -sS --max-time 2 -w "`nHTTP %{http_code}`n" http://127.0.0.1:8080/actuator/health/readiness
```

Với cấu hình của bài, kết quả mong đợi của hai lần gọi lần lượt là:

```text
{"status":"UP"}
HTTP 200
{"status":"OUT_OF_SERVICE"}
HTTP 503
```

Nếu chạy vòng quan sát từ trước, giai đoạn sớm hơn có thể xuất hiện lỗi kết nối và `HTTP 000`. Điều này không mâu thuẫn với các phản hồi sau khi HTTP đã truy cập được.

Sau `WARMUP end` và sau khi availability chuyển sang `ACCEPTING_TRAFFIC`, readiness phải trở thành:

```text
{"status":"UP"}
HTTP 200
```

Các dòng quan trọng do chương trình tự in xuất hiện theo thứ tự sau; phần dấu thời gian của dòng `AVAIL` được lược bỏ trong bản trình bày:

```text
AVAIL LivenessState=CORRECT
WARMUP begin
WARMUP end
AVAIL ReadinessState=ACCEPTING_TRAFFIC
LAB: press Enter to close
```

Log Spring Boot/Tomcat có thể xen giữa các dòng này. Không xem đây là toàn bộ stdout hay một lịch thời gian cố định.

**Giải thích kết quả:** ngữ cảnh đã hoạt động đủ để probe liveness thành công, nhưng công việc khởi động của runner chưa xong. Ứng dụng chưa công bố sẵn sàng nhận lưu lượng.

Nếu bỏ lỡ khoảng 15 giây và chỉ thấy `200`, hãy khởi động lại ứng dụng sau khi đã mở vòng quan sát. Không đổi tên trạng thái hay kết luận cơ chế sai chỉ vì mẫu đầu tiên được lấy quá muộn.

## 7. Thí nghiệm 2 — Chủ động ngừng nhận lưu lượng theo readiness

Chờ ứng dụng sẵn sàng rồi gọi:

```powershell
curl.exe --noproxy "*" -sS -X POST -w "`nHTTP %{http_code}`n" http://127.0.0.1:8080/demo/drain
```

Phản hồi của **lệnh điều khiển** là:

```text
REFUSING_TRAFFIC
HTTP 200
```

`200` ở đây cho biết thao tác đổi trạng thái được xử lý. Nó không phải kết quả probe readiness.

Gọi lại hai probe bằng lệnh của thí nghiệm 1. Liveness vẫn có kết quả `UP / 200`, còn readiness chuyển sang `OUT_OF_SERVICE / 503`.

Tiếp tục gọi trực tiếp endpoint nghiệp vụ:

```powershell
curl.exe --noproxy "*" -sS --max-time 15 -w "`nHTTP %{http_code}`n" http://127.0.0.1:8080/demo/work
```

Sau khoảng 10 giây, kết quả mong đợi là:

```text
completed
HTTP 200
```

Đây là phép kiểm tra quan trọng: chương trình chỉ đổi tín hiệu readiness, còn mã xử lý nghiệp vụ vẫn được ánh xạ và connector vẫn nhận yêu cầu trực tiếp. Bài này chưa có thành phần định tuyến nào đọc readiness để loại phiên bản khỏi danh sách đích.

Đưa ứng dụng về trạng thái sẵn sàng:

```powershell
curl.exe --noproxy "*" -sS -X POST -w "`nHTTP %{http_code}`n" http://127.0.0.1:8080/demo/resume
```

Kết quả của thao tác là `ACCEPTING_TRAFFIC / HTTP 200`; lần kiểm tra readiness sau đó trở lại `UP / HTTP 200`.

Việc công bố `ACCEPTING_TRAFFIC` trong bài là thao tác thủ công có kiểm soát. Một dịch vụ thật chỉ nên công bố trạng thái này khi điều kiện phục vụ đã được khôi phục; không dùng sự kiện để che đi một lỗi chưa được xử lý.

## 8. Thí nghiệm 3 — Đóng ứng dụng khi còn một yêu cầu đang chạy

Mục tiêu là tạo bằng chứng rằng yêu cầu cũ có cơ hội hoàn tất trong lúc việc nhận yêu cầu mới bị dừng.

1. Đảm bảo readiness đang là `UP / 200`.
2. Giữ vòng quan sát probe ở terminal B.
3. Ở terminal C, gọi lại `/demo/work` với `--max-time 15`.
4. Chờ terminal A xuất hiện `WORK begin` của lần gọi vừa tạo.
5. Ngay sau đó, nhấn Enter ở terminal A.

Lệnh ở C:

```powershell
curl.exe --noproxy "*" -sS --max-time 15 -w "`nHTTP %{http_code}`n" http://127.0.0.1:8080/demo/work
```

Phải chờ `WORK begin` rồi mới đóng để biết yêu cầu đã vào phương thức xử lý. Nếu đóng trước khi yêu cầu đến máy chủ, bạn đang kiểm tra khả năng nhận yêu cầu mới, chưa kiểm tra một yêu cầu đang xử lý.

Quan sát các bằng chứng sau:

- Log availability công bố `ReadinessState=REFUSING_TRAFFIC`.
- Listener ghi `CONTEXT closing`.
- Tomcat bắt đầu quá trình tắt có chờ.
- Với yêu cầu đã vào và hoàn tất trong thời hạn chờ, terminal C nhận `completed / HTTP 200`.
- Khi máy chủ đã dừng, probe không còn phản hồi HTTP từ ứng dụng.

Phần hạ tầng thực hiện tắt có chờ gọi `WebServer.shutDownGracefully` trong pha dừng vòng đời; nó không duy trì một máy chủ health riêng để luôn trả kết quả sau khi ứng dụng đã đóng. [WebServerGracefulShutdownLifecycle](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/web/context/WebServerGracefulShutdownLifecycle.java).

**Không yêu cầu vòng lặp bắt buộc thấy 503 trong thí nghiệm này.** Có thể nhìn thấy `200` ở mẫu trước khi đóng, rồi lỗi kết nối ở mẫu kế tiếp. Dùng log sự kiện để xác nhận chuyển trạng thái, thay vì suy ra rằng readiness chưa đổi chỉ vì không bắt được JSON 503.

**Không yêu cầu quá trình tắt phải đợi hết 20 giây.** Nếu yêu cầu đang xử lý kết thúc sớm, máy chủ có thể hoàn thành việc dừng sớm hơn. Thời hạn này cũng không bảo đảm một yêu cầu tùy ý luôn hoàn tất: độ trễ, lỗi xử lý, việc client tự timeout và việc hệ điều hành cưỡng bức dừng tiến trình đều có thể thay đổi kết quả.

Sau khi ứng dụng tắt xong, gọi thêm một lần:

```powershell
curl.exe --noproxy "*" -sS --max-time 2 -w "`nHTTP %{http_code}`n" http://127.0.0.1:8080/actuator/health/readiness
```

Kết quả phù hợp là không nhận được phản hồi HTTP từ tiến trình đã tắt. Không mô tả kết quả này thành `{"status":"DOWN"}` nếu thực tế chỉ có lỗi kết nối.

### Thử bằng tín hiệu dừng của hệ điều hành

Với một ứng dụng chạy ở terminal, Ctrl+C thường kích hoạt đường dừng có xử lý của JVM, nhưng cách IDE hoặc công cụ điều khiển gửi lệnh dừng có thể khác. Trong bài, Enter gọi `context.close()` là cách quan sát chủ động.

Trên Linux, có thể gửi `SIGTERM` tới đúng PID Java để kiểm tra đường dừng bằng tín hiệu. `SIGKILL`, `kill -9`, hoặc một thao tác cưỡng bức kết thúc tiến trình không đại diện cho thí nghiệm tắt có chờ. Không dùng chúng để kết luận rằng Spring Boot đã bỏ qua thời hạn graceful shutdown.

## 9. Liên hệ khi có Kubernetes hoặc bộ cân bằng tải

Trong Kubernetes, readiness thất bại khiến phiên bản bị loại khỏi các đích phục vụ phù hợp của Service; liveness thất bại đủ điều kiện dẫn đến khởi động lại container. Startup probe có thể bảo vệ một ứng dụng khởi động lâu; readiness không thay thế cơ chế bảo vệ đó. Việc kiểm tra có chu kỳ và ngưỡng, nên không nên giả định mọi thành phần bên ngoài thay đổi quyết định ngay trong cùng thời điểm ứng dụng phát sự kiện. [Kubernetes — Liveness, Readiness, and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/).

Khi suy luận về một lần rút phiên bản khỏi lưu lượng, hãy ghi riêng:

1. Thời điểm ứng dụng đổi readiness.
2. Thời điểm bên kiểm tra nhận thấy thay đổi.
3. Thời điểm quyết định định tuyến có hiệu lực.
4. Thời điểm máy chủ bắt đầu và hoàn tất việc dừng.

Bài thực hành cục bộ chỉ đo trực tiếp các mốc thuộc ứng dụng và lời gọi HTTP trực tiếp. Nó chưa chứng minh thời gian lan truyền của một hệ thống định tuyến cụ thể.

Nếu đặt Actuator trên một cổng quản trị khác, hãy ghi cả cổng probe và cổng nghiệp vụ trong bằng chứng. Một kết quả thành công ở cổng quản trị riêng chưa kiểm tra đầy đủ đường đi của yêu cầu nghiệp vụ. Đừng thay một quan sát của cổng này bằng kết luận về cổng kia.

## 10. Các lỗi dễ làm sai kết luận

| Hiện tượng hoặc nhận định | Cách kiểm tra và giải thích |
| --- | --- |
| “Đã có log Started nên readiness phải thành công” | Đối chiếu `WARMUP end` và sự kiện `ACCEPTING_TRAFFIC`; runner có thể còn đang chạy |
| “Readiness 503 nên JVM đã hỏng” | Kiểm tra liveness và log; rút khỏi lưu lượng có thể là thao tác chủ động |
| “Drain xong mà curl nghiệp vụ vẫn thành công là sai” | Xem phương thức drain có đóng connector hay chỉ phát sự kiện; curl trực tiếp không đi qua bộ định tuyến |
| Chỉ kiểm tra `/actuator/health` | Gọi đúng hai nhóm `/health/liveness` và `/health/readiness`; health tổng hợp không thay cho phép đo từng nhóm |
| `404` khi gọi probe | Kiểm tra đường dẫn, cổng, cấu hình bật nhóm và exposure; không coi là kết quả `OUT_OF_SERVICE` |
| `401`, `403` hoặc chuyển hướng đăng nhập | Kiểm tra cấu hình bảo mật thực tế; đây không phải mã trạng thái availability |
| Curl hiển thị `000` | Đọc lỗi kết nối/timeout và mã thoát; không gọi nó là HTTP 503 |
| Tắt xong không thấy readiness 503 | Đối chiếu log availability; máy chủ có thể đã ngừng nhận kết nối trước mẫu tiếp theo |
| Không thấy cửa sổ warmup | Mở vòng quan sát trước khi chạy lại ứng dụng; không tự kéo dài mọi giai đoạn trong mô tả lý thuyết |
| Yêu cầu cũ không hoàn tất | Kiểm tra `WORK begin`, thời hạn phía client, thời hạn dừng, lỗi xử lý và cách kết thúc tiến trình |
| Chỉ nhìn một mẫu health rồi suy toàn bộ vòng đời | Ghi chuỗi quan sát có thời gian và đối chiếu với log cùng lần chạy |

## 11. Tự kiểm tra bằng bằng chứng

Lập bảng cho chính lần chạy của bạn; ghi kết quả thực tế và thời điểm thay vì chép một chuỗi thời gian có sẵn:

| Giai đoạn thực nghiệm | Bằng chứng cần lưu |
| --- | --- |
| Chưa mở được HTTP | Lỗi curl, mã thoát, có hay không có mã HTTP |
| Runner đang chờ | Log `WARMUP begin`, kết quả của cả hai probe |
| Đã sẵn sàng | Sự kiện `ACCEPTING_TRAFFIC`, readiness thành công |
| Đã drain | Phản hồi POST, readiness thất bại, liveness còn thành công |
| Gọi trực tiếp trong lúc drain | Kết quả `/demo/work` và giải thích vai trò của bộ định tuyến |
| Đang đóng với yêu cầu cũ | `WORK begin`, sự kiện từ chối lưu lượng, log đóng ngữ cảnh, kết quả client |
| Đã tắt | Lần gọi probe không nhận HTTP từ ứng dụng |

Trả lời các câu hỏi sau dựa trên các bằng chứng đó:

1. Vì sao cùng một lần khởi động có thể quan sát `liveness=200` và `readiness=503`?
2. Trong mã ví dụ, chính câu lệnh nào đổi readiness? Có câu lệnh nào ở đó chặn mọi yêu cầu nghiệp vụ không?
3. Vì sao POST `/demo/drain` trả 200 trong khi GET probe readiness trả 503?
4. Nếu shutdown chỉ cho thấy chuỗi “200 rồi lỗi kết nối”, cần dùng bằng chứng nào để xác nhận ứng dụng đã từ chối lưu lượng về mặt trạng thái?
5. Vì sao yêu cầu đang xử lý và yêu cầu mới sau khi bắt đầu đóng có thể có kết quả khác nhau?
6. Khi nào phép đo ở một cổng quản trị riêng chưa đủ để khẳng định cổng nghiệp vụ hoạt động?

Kết quả học tập cần đạt là giải thích được từng quan sát bằng đúng lớp cơ chế: sự kiện và trạng thái nội bộ, phép chiếu health/HTTP, quyết định định tuyến, và hành vi dừng của máy chủ.

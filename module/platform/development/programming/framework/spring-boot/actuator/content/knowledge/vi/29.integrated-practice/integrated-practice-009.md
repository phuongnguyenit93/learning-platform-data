# Kiểm chứng quy trình khởi động, readiness và graceful shutdown

## 1. Bài thực hành cần chứng minh điều gì?

Một ứng dụng có thể đã mở cổng HTTP nhưng vẫn đang nạp dữ liệu cần thiết. Khi triển khai phiên bản mới, gửi yêu cầu nghiệp vụ vào thời điểm đó dễ gây lỗi. Ở chiều ngược lại, khi dừng phiên bản cũ, ngắt tiến trình ngay lập tức có thể làm hỏng yêu cầu đang xử lý.

Bài này dùng một ứng dụng Spring MVC với Actuator để kiểm chứng toàn bộ vòng đời:

1. **Khởi động:** máy chủ HTTP được tạo, sau đó tác vụ chuẩn bị dữ liệu chạy.
2. **Sẵn sàng nhận lưu lượng (readiness):** chỉ cho phép chuyển lưu lượng đến phiên bản này khi phần chuẩn bị bắt buộc đã hoàn tất.
3. **Dừng có thời gian chờ (graceful shutdown):** ngừng nhận yêu cầu mới và dành thời gian cho yêu cầu đã nhận hoàn thành.

Mục tiêu là thu được bằng chứng từ **mã HTTP, nội dung phản hồi, dấu mốc nhật ký và thời điểm tiến trình kết thúc**. Chỉ nhìn dòng `Started ...` hoặc thấy tiến trình Java còn tồn tại chưa đủ.

Thí nghiệm cố định **Java 21, Spring Boot 3.3.0, Spring MVC và Tomcat nhúng**. Đây là một dự án độc lập để học cơ chế, không cần cơ sở dữ liệu hay Kubernetes. Maven được dùng để đóng gói ví dụ; cùng các thư viện đó, hành vi vòng đời không phụ thuộc việc dự án chính dùng Maven hay Gradle.

## 2. Mô hình cần nắm trước khi chạy

### 2.1. Liveness và readiness trả lời hai câu hỏi khác nhau

| Tín hiệu | Câu hỏi | Trạng thái do Spring Boot quản lý | Hành động thường tương ứng ở bộ điều phối |
| --- | --- | --- | --- |
| Liveness | Bản thân tiến trình có còn ở trạng thái có thể hoạt động? | `LivenessState.CORRECT` hoặc `BROKEN` | Có thể khởi động lại phiên bản nếu liveness thất bại đủ ngưỡng |
| Readiness | Phiên bản này đã nên nhận lưu lượng nghiệp vụ chưa? | `ReadinessState.ACCEPTING_TRAFFIC` hoặc `REFUSING_TRAFFIC` | Đưa phiên bản vào hoặc ra khỏi tập đích nhận lưu lượng |

Một ứng dụng đang chuẩn bị dữ liệu có thể **liveness đạt nhưng readiness chưa đạt**. Khởi động lại nó liên tục trong giai đoạn này có thể khiến việc chuẩn bị không bao giờ hoàn thành.

Các trạng thái trên nằm trong `ApplicationAvailability`. Actuator chiếu chúng thành health group phục vụ thăm dò. Trong cấu hình của bài:

- `/actuator/health/liveness`: nhóm liveness.
- `/actuator/health/readiness`: nhóm readiness.
- `/livez` và `/readyz`: đường dẫn bổ sung tương ứng, cùng cổng với API nghiệp vụ.

Readiness thất bại không tự biến mọi Controller thành HTTP 503. Một bộ cân bằng tải phải thực sự sử dụng kết quả thăm dò để ngừng gửi lưu lượng. Nếu muốn ứng dụng tự từ chối yêu cầu khi chưa sẵn sàng, phải có kiểm tra riêng; ví dụ dưới đây chủ động thêm kiểm tra đó để quan sát.

### 2.2. Các mốc khởi động cần phân biệt

Với ví dụ đồng bộ trong bài, thứ tự liên quan là:

```text
Tạo và làm mới ApplicationContext, khởi động máy chủ nhúng
    -> ApplicationStartedEvent
    -> liveness chuyển sang CORRECT
    -> ApplicationRunner thực hiện phần chuẩn bị bắt buộc
    -> ApplicationReadyEvent
    -> readiness chuyển sang ACCEPTING_TRAFFIC
```

Khoảng chờ được đặt trong `ApplicationRunner` để tạo ra một cửa sổ quan sát: HTTP đã có thể trả lời nhưng readiness vẫn từ chối lưu lượng. Dòng nhật ký `Started ...` của Spring Boot xuất hiện trước khi toàn bộ runner hoàn tất, vì vậy không dùng nó làm điều kiện duy nhất để chuyển lưu lượng.

`ApplicationReadyEvent` và sự kiện availability tiếp theo là hai dấu mốc riêng. Nếu đang cần xác nhận **trạng thái** readiness, hãy đọc probe hoặc `ApplicationAvailability`, thay vì coi tên sự kiện là chính trạng thái ấy.

## 3. Tạo ứng dụng thí nghiệm hoàn chỉnh

Chuẩn bị JDK 21, Maven 3.6.3 trở lên, `curl`, ba cửa sổ terminal và cổng 18080 còn trống. Những lệnh PowerShell dưới đây dùng `curl.exe` để tránh nhầm với bí danh `curl` trên một số phiên bản PowerShell.

Tạo thư mục `lifecycle-lab` có cấu trúc:

```text
lifecycle-lab/
├── pom.xml
└── src/main/
    ├── java/com/example/lifecycle/
    │   ├── LifecycleLabApplication.java
    │   └── WorkController.java
    └── resources/
        └── application.yml
```

### 3.1. Tệp pom.xml

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

    <groupId>com.example</groupId>
    <artifactId>lifecycle-lab</artifactId>
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

Không cần tự thêm phiên bản cho từng thư viện Spring, Micrometer hoặc Tomcat; parent quản lý một tập phiên bản tương thích.

### 3.2. Tệp application.yml

```yaml
server:
  address: 127.0.0.1
  port: 18080
  shutdown: graceful

spring:
  application:
    name: lifecycle-lab
  lifecycle:
    timeout-per-shutdown-phase: 20s

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      show-details: never

lab:
  warmup-ms: 15000
  fail-warmup: false
```

Ý nghĩa của các lựa chọn:

- `probes.enabled=true` bật nhóm liveness/readiness ngay cả khi chạy máy cá nhân.
- `add-additional-paths=true` tạo `/livez` và `/readyz` trên máy chủ chính. Probe cùng cổng giúp kiểm tra cả khả năng phục vụ HTTP của ứng dụng.
- `server.shutdown=graceful` được khai báo rõ cho thí nghiệm Spring Boot 3.3.
- `timeout-per-shutdown-phase=20s` là giới hạn chờ của **mỗi giai đoạn dừng**, không phải cam kết toàn tiến trình luôn thoát trong đúng 20 giây.
- Chỉ expose `health`; bài không sử dụng endpoint HTTP `shutdown`.
- Địa chỉ loopback giới hạn máy chủ trong máy đang thực hành. Khi chuyển sang container, cần cấu hình địa chỉ nghe phù hợp trước khi dùng probe từ bên ngoài.

### 3.3. Tệp LifecycleLabApplication.java

```java
package com.example.lifecycle;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LifecycleLabApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(LifecycleLabApplication.class);

        application.addListeners(
                (ApplicationListener<ApplicationEvent>) event -> {
                    if (event instanceof ApplicationStartedEvent) {
                        System.out.println("EVENT_STARTED");
                    } else if (event instanceof ApplicationReadyEvent) {
                        System.out.println("EVENT_READY");
                    } else if (event instanceof AvailabilityChangeEvent<?> change) {
                        System.out.println(
                                "AVAILABILITY " + change.getState());
                    }
                });

        application.run(args);
    }

    @Bean
    ApplicationRunner warmup(
            @Value("${lab.warmup-ms:15000}") long warmupMs,
            @Value("${lab.fail-warmup:false}") boolean failWarmup) {

        return args -> {
            if (warmupMs < 0) {
                throw new IllegalArgumentException(
                        "lab.warmup-ms must be non-negative");
            }

            System.out.println("WARMUP_BEGIN");
            Thread.sleep(warmupMs);

            if (failWarmup) {
                throw new IllegalStateException(
                        "Simulated mandatory warmup failure");
            }

            System.out.println("WARMUP_END");
        };
    }
}
```

Listener được đăng ký vào `SpringApplication` trước `run`, giúp thu các mốc cần quan sát. `Thread.sleep` mô phỏng việc chuẩn bị bắt buộc như nạp một bảng tra cứu. Trong ứng dụng thật, thay nó bằng công việc có kết quả kiểm tra được.

Ở đây runner chạy đồng bộ. Nếu runner chỉ gửi công việc sang một luồng nền rồi trả về ngay, Spring Boot có thể đánh dấu sẵn sàng trong khi công việc nền chưa xong. Muốn công việc đó là điều kiện bắt buộc của readiness, cần thiết kế cơ chế hoàn tất/kiểm tra tương ứng.

### 3.4. Tệp WorkController.java

```java
package com.example.lifecycle;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WorkController {

    private final ApplicationAvailability availability;

    public WorkController(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @GetMapping(value = "/work",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> work(
            @RequestParam(name = "ms", defaultValue = "1000") long ms)
            throws InterruptedException {

        if (ms < 0 || ms > 60000) {
            return ResponseEntity.badRequest()
                    .body("ms must be between 0 and 60000\n");
        }

        if (availability.getReadinessState()
                != ReadinessState.ACCEPTING_TRAFFIC) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("NOT_READY\n");
        }

        System.out.println("WORK_BEGIN ms=" + ms);
        Thread.sleep(ms);
        System.out.println("WORK_END ms=" + ms);

        return ResponseEntity.ok("DONE ms=" + ms + "\n");
    }
}
```

Có hai điểm chủ đích:

1. Kiểm tra readiness ở đầu phương thức là **logic do ứng dụng viết**, không phải khả năng chặn mọi API tự động của Actuator.
2. Khi yêu cầu đã đi qua kiểm tra và bắt đầu xử lý, phương thức không kiểm tra readiness lần nữa. Vì vậy, chuyển sang `REFUSING_TRAFFIC` lúc dừng không làm phương thức tự từ bỏ công việc đang chạy.

Việc ngủ trong luồng xử lý HTTP chỉ phục vụ thí nghiệm một yêu cầu có thời lượng rõ. Nó không phải mẫu thiết kế xử lý công việc dài cho hệ thống thực tế.

### 3.5. Biên dịch và đóng gói

Từ thư mục chứa `pom.xml`, chạy:

```powershell
java -version
mvn -version
mvn clean package
```

Cả Java chạy trực tiếp và Java mà Maven sử dụng cần là JDK 21. Sau khi Maven báo build thành công, có tệp `target/lifecycle-lab-1.0.0.jar`. Không chạy tệp có hậu tố `.original`.

Đây là chương trình Spring Boot nhiều tệp, phải biên dịch với các dependency tương ứng. Chạy riêng `javac WorkController.java` khi thiếu classpath Spring sẽ không đủ.

## 4. Thí nghiệm A: HTTP mở trước khi readiness đạt

### 4.1. Chuẩn bị cửa sổ quan sát

Mở terminal B trước, rồi chạy vòng thăm dò:

```powershell
1..40 | ForEach-Object {
    $liveCode = & curl.exe -s -o NUL -w "%{http_code}" --connect-timeout 1 --max-time 2 http://127.0.0.1:18080/livez 2>$null
    $readyCode = & curl.exe -s -o NUL -w "%{http_code}" --connect-timeout 1 --max-time 2 http://127.0.0.1:18080/readyz 2>$null
    "{0:HH:mm:ss} live={1} ready={2}" -f (Get-Date), $liveCode, $readyCode
    Start-Sleep -Seconds 1
}
```

`000` do curl in ra khi chưa nhận được mã trạng thái HTTP; đó không phải mã HTTP do ứng dụng trả về. Hai lần gọi được thực hiện liên tiếp nên không coi chúng là một ảnh chụp hoàn toàn đồng thời.

Ở terminal A, khởi động ứng dụng:

```powershell
java -jar target/lifecycle-lab-1.0.0.jar
```

Vòng thăm dò chạy trước ứng dụng giúp tránh bỏ lỡ toàn bộ cửa sổ chuẩn bị 15 giây. Nếu vẫn thao tác không kịp, khởi động lại với `--lab.warmup-ms=30000`.

### 4.2. Đối chiếu trạng thái quan sát được

| Giai đoạn | Liveness | Readiness | Điều được chứng minh |
| --- | --- | --- | --- |
| Tiến trình chưa mở cổng | Chưa có phản hồi HTTP | Chưa có phản hồi HTTP | Chưa thể suy ra health từ một phản hồi chưa tồn tại |
| Đã đến `WARMUP_BEGIN`, chưa đến `WARMUP_END` | Thường quan sát được 200 | 503 | Ứng dụng sống nhưng chưa sẵn sàng |
| Đã hoàn tất khởi động | 200 | 200 | Phiên bản đã sẵn sàng theo nhóm readiness hiện tại |

Các cửa sổ chuyển tiếp rất ngắn có thể không xuất hiện trong lần lấy mẫu. Điều cần bắt được là khoảng runner đang chờ đủ dài, có liveness 200 và readiness 503, rồi readiness chuyển 200 sau khi chuẩn bị xong.

Trong cửa sổ chuẩn bị, ở terminal C chạy:

```powershell
curl.exe -i --max-time 2 http://127.0.0.1:18080/actuator/health/liveness
curl.exe -i --max-time 2 http://127.0.0.1:18080/actuator/health/readiness
curl.exe -i --max-time 2 "http://127.0.0.1:18080/work?ms=0"
```

Với cấu hình mặc định của ví dụ, các phần phản hồi cần đối chiếu là:

```text
GET /actuator/health/liveness
HTTP 200
{"status":"UP"}

GET /actuator/health/readiness
HTTP 503
{"status":"OUT_OF_SERVICE"}

GET /work?ms=0
HTTP 503
NOT_READY
```

Đây là **các phần cần kiểm tra** của ba phản hồi, không phải toàn bộ stdout của `curl -i`. Dòng HTTP thực tế còn có phiên bản giao thức và các header phụ thuộc máy chủ.

### 4.3. Đối chiếu nhật ký khởi động

Các dòng do chính mã ví dụ in ra khi khởi động thành công có thứ tự:

```text
EVENT_STARTED
AVAILABILITY CORRECT
WARMUP_BEGIN
WARMUP_END
EVENT_READY
AVAILABILITY ACCEPTING_TRAFFIC
```

Nhật ký Spring/Tomcat có thể xuất hiện xen giữa. Không dùng số giây hoặc vị trí tuyệt đối của các dòng hệ thống làm điều kiện kiểm tra.

Sau `ACCEPTING_TRAFFIC`, gọi lại:

```powershell
curl.exe -i --max-time 2 http://127.0.0.1:18080/readyz
curl.exe -i --max-time 2 "http://127.0.0.1:18080/work?ms=0"
```

Kết quả tương ứng cần là readiness HTTP 200 và yêu cầu nghiệp vụ HTTP 200 có thân:

```text
DONE ms=0
```

**Tiêu chí đạt A:** ghi nhận được giai đoạn liveness 200/readiness 503 trong lúc chuẩn bị, readiness 200 sau khi chuẩn bị hoàn tất, và `/work` chuyển từ từ chối sang xử lý thành công.

## 5. Thí nghiệm B: giữ yêu cầu đang chạy khi dừng

### 5.1. Bắt đầu một yêu cầu đủ dài

Giữ ứng dụng đã sẵn sàng ở terminal A. Ở terminal B chạy:

```powershell
curl.exe -i --max-time 30 "http://127.0.0.1:18080/work?ms=10000"
```

Chờ terminal A xuất hiện:

```text
WORK_BEGIN ms=10000
```

Dấu mốc này chứng minh phương thức đã nhận và bắt đầu xử lý yêu cầu. Việc chỉ khởi chạy curl chưa đủ, vì yêu cầu có thể chưa vào đến Controller.

### 5.2. Yêu cầu tiến trình dừng bình thường

Ngay sau `WORK_BEGIN`, nhấn **Ctrl+C tại terminal A đang chạy trực tiếp `java -jar`**. JVM cần có cơ hội chạy shutdown hook và đóng Spring context.

Nếu chạy bằng Linux/macOS, có thể gửi `SIGTERM` từ terminal khác:

```bash
kill -TERM <java-pid>
```

Trong lệnh minh họa này, thay `<java-pid>` bằng PID của đúng tiến trình thí nghiệm đã xác minh. Không gửi tín hiệu cho mọi tiến trình Java.

Nút Stop của IDE có thể kết thúc tiến trình theo cách khác. `kill -9`, `taskkill /F` hoặc thao tác cưỡng bức tương tự không dùng được để chứng minh graceful shutdown.

### 5.3. Thu bằng chứng

Với yêu cầu 10 giây và thời gian chờ 20 giây, khi yêu cầu dừng được gửi đủ sớm, cần quan sát:

- Availability chuyển sang `REFUSING_TRAFFIC`.
- Yêu cầu đã vào Controller vẫn in `WORK_END ms=10000`.
- Curl ở terminal B nhận HTTP 200 và thân `DONE ms=10000`.
- Tiến trình kết thúc sau khi phần xử lý còn lại hoàn tất; không cần chờ hết toàn bộ 20 giây nếu công việc đã xong.

Thân phản hồi nghiệp vụ:

```text
DONE ms=10000
```

Khi vừa gửi yêu cầu dừng, dùng terminal C thử **kết nối mới**:

```powershell
curl.exe --http1.1 -i -H "Connection: close" --connect-timeout 1 --max-time 2 "http://127.0.0.1:18080/work?ms=0"
curl.exe --http1.1 -i -H "Connection: close" --connect-timeout 1 --max-time 2 http://127.0.0.1:18080/readyz
```

Với Tomcat nhúng, máy chủ ngừng nhận kết nối ở tầng mạng khi bước graceful stop đã bắt đầu. Vì vậy, yêu cầu mới có thể bị từ chối kết nối hoặc không nhận được phản hồi HTTP. Không đặt điều kiện rằng mọi yêu cầu sau Ctrl+C nhất thiết nhận HTTP 503.

Có một khoảng chuyển tiếp: một yêu cầu vẫn kịp vào trước khi connector dừng có thể bị kiểm tra readiness của Controller trả 503. Với kết nối giữ lâu hoặc máy chủ nhúng khác, cách từ chối cũng có thể khác. Phân biệt rõ:

- **503:** đã có phản hồi HTTP từ máy chủ.
- **Lỗi kết nối/000 của curl:** không có mã trạng thái HTTP để đánh giá.
- **Yêu cầu đang chạy trả 200:** bằng chứng trực tiếp rằng công việc được tiếp tục trong thời gian chờ.

Probe readiness cũng có thể không gọi được sau khi connector dừng. Điều đó không phủ nhận trạng thái `REFUSING_TRAFFIC` đã xuất hiện trong nhật ký trước đó.

**Tiêu chí đạt B:** cùng một yêu cầu đã có `WORK_BEGIN` trước khi dừng được hoàn thành với phản hồi đúng, trong khi kết nối mới bị ngăn sau khi máy chủ bước vào giai đoạn dừng.

## 6. Thí nghiệm C: phần chuẩn bị bắt buộc thất bại

Đảm bảo tiến trình trước đã kết thúc. Chạy lại vòng thăm dò ở terminal B, rồi ở terminal A chạy:

```powershell
java -jar target/lifecycle-lab-1.0.0.jar --lab.warmup-ms=10000 --lab.fail-warmup=true
```

Kỳ vọng:

1. Có `WARMUP_BEGIN`.
2. Runner ném lỗi `Simulated mandatory warmup failure`.
3. Không có `WARMUP_END`, `EVENT_READY` hoặc `AVAILABILITY ACCEPTING_TRAFFIC` của lần chạy này.
4. Tiến trình dừng với lỗi, không tồn tại mãi như một phiên bản đã sẵn sàng.

Ngay khi lệnh Java kết thúc, ở cùng terminal PowerShell đọc:

```powershell
$LASTEXITCODE
```

Mã thoát phải khác 0. Không chạy một lệnh chương trình ngoài khác trước khi đọc, vì nó có thể làm thay đổi `$LASTEXITCODE`.

Readiness không nên chuyển 200 trong lần chạy lỗi. Tuy nhiên, riêng việc không bắt được 200 trong vòng thăm dò chưa đủ chứng minh: thăm dò có thể bỏ lỡ sự kiện ngắn. Kết hợp nó với nhật ký không có mốc accepting và lỗi của runner.

**Tiêu chí đạt C:** việc chuẩn bị bắt buộc thất bại ngăn ứng dụng đi tới readiness chấp nhận lưu lượng.

## 7. Thí nghiệm D: công việc vượt quá thời gian chờ

Khởi động một lần chạy mới:

```powershell
java -jar target/lifecycle-lab-1.0.0.jar --lab.warmup-ms=0 --spring.lifecycle.timeout-per-shutdown-phase=3s
```

Sau khi readiness đạt 200, ở terminal B chạy:

```powershell
curl.exe -i --max-time 45 "http://127.0.0.1:18080/work?ms=30000"
```

Chờ `WORK_BEGIN ms=30000`, rồi gửi yêu cầu dừng như thí nghiệm B. Lúc này, công việc còn lại dài hơn đáng kể so với ngân sách chờ 3 giây.

Quan sát nhật ký về việc hết thời gian chờ của giai đoạn graceful shutdown. Sau khi vượt ngân sách, quá trình đóng context tiếp tục; ứng dụng **không còn bảo đảm** yêu cầu dài được hoàn tất thành công. Tùy thời điểm, máy chủ và quá trình giải phóng tài nguyên, client có thể thấy kết nối bị đóng hoặc lỗi khác. Không gán một mã HTTP cố định cho tình huống đó.

Không suy luận rằng:

- Tất cả luồng Java bị cưỡng bức ngắt chính xác ở giây thứ 3.
- Toàn bộ JVM chắc chắn thoát trong đúng 3 giây.
- Một lần client tình cờ nhận 200 sau khi vượt ngân sách là cam kết hoàn tất cho mọi trường hợp.

`timeout-per-shutdown-phase` giới hạn việc chờ của từng giai đoạn trong cơ chế lifecycle. Các giai đoạn khác, callback giải phóng tài nguyên và việc dừng máy chủ còn có thể ảnh hưởng tổng thời gian.

**Tiêu chí đạt D:** phân biệt được trường hợp công việc hoàn tất trong ngân sách và trường hợp ngân sách graceful bị vượt, có bằng chứng từ nhật ký và kết quả client.

## 8. Từ thí nghiệm cục bộ đến triển khai có bộ cân bằng tải

### 8.1. Probe phải điều khiển lưu lượng thật

Trên máy cá nhân, gọi `/readyz` chỉ quan sát trạng thái. Trong môi trường triển khai, cần có thành phần đọc kết quả đó và cập nhật danh sách đích nhận lưu lượng.

Luồng triển khai an toàn cần kiểm chứng riêng:

```text
Phiên bản mới khởi động
    -> phần chuẩn bị hoàn tất
    -> readiness đạt
    -> bộ điều phối đưa phiên bản mới vào tập đích

Phiên bản cũ bị loại khỏi tập đích
    -> thay đổi được truyền tới các tầng định tuyến
    -> nhận yêu cầu dừng
    -> xử lý nốt công việc đã nhận trong ngân sách
    -> kết thúc
```

Đây là mục tiêu phối hợp giữa nhiều thành phần, không phải lời hứa rằng mọi nền tảng luôn thực hiện chúng tuần tự tuyệt đối. Khi dừng một Pod, cập nhật endpoint và tín hiệu dừng có thể có độ trễ hoặc diễn ra gần nhau. Vì thế, thí nghiệm với một tiến trình không đủ chứng minh không mất yêu cầu khi triển khai thật.

Nếu dùng Kubernetes:

- Startup probe bảo vệ cửa sổ khởi động dài khỏi việc liveness kiểm tra quá sớm.
- Readiness probe quyết định phiên bản có thuộc tập đích sẵn sàng hay không.
- Liveness probe phát hiện tình trạng cần khởi động lại; không nên phụ thuộc tùy tiện vào mọi dịch vụ ngoài.
- Cấu hình probe đúng cổng/đường dẫn, dùng `/livez` và `/readyz` khi đã bật đường dẫn bổ sung.
- Ghi đè `server.address` thành địa chỉ nghe phù hợp, chẳng hạn `0.0.0.0` trong container; địa chỉ loopback của bài không phục vụ probe gửi đến IP của Pod.

Các health group mặc định dựa trên trạng thái availability không tự chứng minh toàn bộ chức năng nghiệp vụ hay mọi kết nối ngoài đều hoạt động. Chỉ đưa phụ thuộc vào readiness khi việc mất phụ thuộc ấy thực sự có nghĩa phiên bản không nên nhận lưu lượng; tránh tạo việc khởi động lại hàng loạt chỉ vì một dịch vụ dùng chung tạm thời lỗi.

### 8.2. Phối hợp các ngân sách thời gian

Phải phân biệt ít nhất bốn thời gian:

| Ngân sách | Vai trò |
| --- | --- |
| Thời gian request được chấp nhận xử lý | Giới hạn công việc mà ứng dụng định hoàn thành |
| Timeout của client/proxy | Client hoặc proxy sẵn lòng chờ bao lâu |
| Timeout lifecycle của ứng dụng | Mỗi giai đoạn đóng context được chờ bao lâu |
| Thời gian nền tảng cho container kết thúc | Khi nào nền tảng sẽ chuyển sang cưỡng bức kết thúc |

Ví dụ lập kế hoạch: request cần tối đa 10 giây, graceful phase cho 20 giây, container có 40 giây. Những con số này tạo khoảng dự phòng nhưng chưa tự chứng minh đủ: cần cộng thời gian xử lý trước dừng, độ trễ định tuyến, các giai đoạn đóng khác và dự phòng.

Nếu cấu hình `preStop` trong Kubernetes, thời gian thực hiện hook cũng sử dụng ngân sách kết thúc của Pod. Không xem một lệnh ngủ cố định là bằng chứng rằng mọi bộ cân bằng tải đã cập nhật xong.

Cũng không để timeout curl ngắn hơn công việc đang thử, rồi quy lỗi client hết thời gian chờ cho graceful shutdown.

### 8.3. Giới hạn của kết luận

Graceful shutdown của máy chủ HTTP không tự cung cấp:

- Cơ chế xử lý lại công việc sau khi tiến trình bị cưỡng bức dừng.
- Bảo đảm giao dịch nghiệp vụ chỉ thực hiện đúng một lần.
- Chờ mọi tác vụ bất đồng bộ đã tách khỏi vòng đời request.
- Cơ chế hoàn tất an toàn cho mọi consumer, scheduler hoặc executor tự tạo.

Các thành phần đó cần hợp đồng dừng và khôi phục riêng. Với một thao tác ghi quan trọng, vẫn cần thiết kế giao dịch, tính lặp an toàn và cách client xác định kết quả khi kết nối mất.

## 9. Chẩn đoán kết quả lệch kỳ vọng

| Hiện tượng | Kiểm tra trước | Cách xử lý trong thí nghiệm |
| --- | --- | --- |
| Probe trả 404 | Có starter Actuator, đúng đường dẫn và đã bật probes? | Kiểm tra cấu hình `probes.enabled` và `add-additional-paths`, chạy đúng JAR vừa build |
| Probe trả 401/403 | Dự án có thêm Spring Security hoặc proxy xác thực? | Đối chiếu chính sách cho probe; ví dụ nguyên bản không thêm Security |
| Không bắt được readiness 503 | Có mở vòng thăm dò trước khi chạy Java? Runner có thực sự chờ? | Tăng `lab.warmup-ms`, đối chiếu `WARMUP_BEGIN/END` |
| Readiness đạt quá sớm trong mã thực tế | Runner chỉ khởi chạy tác vụ nền rồi trả về? | Đưa điều kiện hoàn tất bắt buộc vào cơ chế readiness đúng thiết kế |
| Readiness 503 nhưng API vẫn trả 200 ở ứng dụng khác | Có bộ định tuyến hoặc kiểm tra chặn yêu cầu chưa? | Phân biệt tín hiệu readiness với cơ chế thực sự điều khiển lưu lượng |
| Ctrl+C làm request mất ngay | Có đúng tiến trình `java -jar`, đúng `server.shutdown`, đúng tín hiệu dừng? | Lặp lại với một request đã có `WORK_BEGIN`, không dùng force kill |
| Yêu cầu mới không trả 503 mà lỗi kết nối | Tomcat đã dừng nhận kết nối? | Đây là kết quả có thể đúng; phân biệt lỗi transport với mã HTTP |
| Curl hết thời gian chờ trước công việc | `--max-time` có ngắn hơn thời lượng thử? | Dùng ngân sách client đủ dài |
| Bị lỗi cổng đang dùng | Tiến trình lần trước đã kết thúc? | Xác minh PID của thí nghiệm; chỉ dừng đúng tiến trình đó hoặc đổi cổng nhất quán |
| Graceful chờ lâu hơn con số cấu hình | Đang đo một phase hay cả JVM? Có callback/luồng khác? | Thu nhật ký lifecycle và đo từng phần trước khi kết luận |

Nếu đổi cổng, đổi nhất quán cấu hình và mọi lệnh probe. Nếu thay Tomcat bằng máy chủ khác hoặc chuyển sang WebFlux, cần chạy lại thí nghiệm về yêu cầu mới và đang chạy; không bê nguyên kỳ vọng tầng kết nối.

## 10. Hồ sơ bằng chứng để tự nghiệm thu

Với từng lần chạy, ghi phiên bản Java/Spring Boot, tham số dòng lệnh, thời điểm bắt đầu/dừng và các dòng nhật ký thuộc đúng tiến trình. Không ghép `WORK_BEGIN` của lần này với phản hồi của lần khác.

| Thử nghiệm | Bằng chứng bắt buộc | Điều chưa được suy ra chỉ từ kết quả này |
| --- | --- | --- |
| A — khởi động chậm | Readiness 503 khi chuẩn bị; sau đó 200; mốc chuẩn bị và availability khớp | Mọi phụ thuộc nghiệp vụ đều khỏe |
| B — request trong ngân sách | `WORK_BEGIN` trước yêu cầu dừng; `WORK_END` và phản hồi 200 sau đó | Mọi loại tác vụ nền cũng được chờ |
| C — chuẩn bị thất bại | Lỗi runner, không có accepting của lần chạy, mã thoát khác 0 | Mọi lỗi runtime đều phải làm liveness hỏng |
| D — vượt ngân sách | Nhật ký hết thời gian chờ và kết quả client được ghi nhận | Một mã HTTP hoặc thời điểm thoát cố định |

Tự trả lời sau khi chạy:

1. Vì sao cổng HTTP đã mở và liveness 200 vẫn chưa đủ để gửi lưu lượng nghiệp vụ?
2. Dòng `Started ...` xuất hiện trong khi runner đang chuẩn bị có mâu thuẫn với readiness 503 không?
3. Tại sao readiness thất bại không tự chặn mọi Controller?
4. Vì sao probe không kết nối được trong lúc dừng không đồng nghĩa health endpoint đã trả 503?
5. Bạn có bằng chứng nào cho thấy yêu cầu dài đã thực sự vào Controller trước khi gửi yêu cầu dừng?
6. Những giới hạn nào khiến graceful shutdown không thay thế được thiết kế khôi phục nghiệp vụ?

Sau thực hành, chờ hoặc yêu cầu dừng bình thường đúng tiến trình của bài, xác minh cổng thí nghiệm không còn phục vụ. Không cần bật endpoint shutdown, expose toàn bộ Actuator hay sửa chính sách bảo mật của một ứng dụng đang dùng thật để hoàn thành bài này.

## Tài liệu đối chiếu

- [Spring Boot 3.3 — SpringApplication và application availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html).
- [Spring Boot 3.3 — Actuator endpoints và Kubernetes probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).
- [Spring Boot 3.3 — Graceful shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html).

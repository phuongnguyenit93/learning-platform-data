# Phân biệt liveness, readiness và startup probe

## 1. Ba phép kiểm tra trả lời ba câu hỏi khác nhau

Một tiến trình Java vẫn tồn tại chưa đủ để kết luận ứng dụng có thể phục vụ người dùng. Ví dụ, máy chủ HTTP đã mở cổng nhưng dữ liệu tra cứu đang được nạp; hoặc ứng dụng tạm ngừng nhận yêu cầu mới để tự khôi phục. Nếu cứ khởi động lại trong cả hai tình huống, ứng dụng có thể không bao giờ hoàn thành công việc đang làm.

**Probe** là phép kiểm tra mà kubelet, thành phần quản lý container trên mỗi node Kubernetes, thực hiện và dùng kết quả để quyết định hành động. Trong bài này, probe dùng HTTP để đọc tín hiệu do Spring Boot Actuator cung cấp.

| Loại | Câu hỏi cần trả lời | Hành động khi thất bại đủ ngưỡng | Vòng đời |
| --- | --- | --- | --- |
| Liveness | Trạng thái bên trong của bản chạy còn hoạt động đúng, hoặc có thể tự hồi phục không? | Kubelet dừng container; việc chạy lại tuân theo chính sách khởi động lại | Kiểm tra định kỳ sau giai đoạn startup nếu có startup probe |
| Readiness | Bản chạy hiện tại đã sẵn sàng nhận lưu lượng chưa? | Đánh dấu không sẵn sàng để ngừng đưa lưu lượng Service tới Pod; container tiếp tục chạy | Kiểm tra lặp lại, có thể chuyển qua lại giữa sẵn sàng và chưa sẵn sàng |
| Startup | Lần khởi động hiện tại đã vượt qua mốc khởi tạo được chọn chưa? | Dừng container nếu hết số lần thử cho phép; việc chạy lại tuân theo chính sách | Dừng kiểm tra sau lần thành công đầu tiên; được thực hiện lại khi container khởi động lại |

Khi có startup probe, kubelet chưa chạy liveness và readiness probe cho đến khi startup probe thành công. Khi đó, liveness và readiness làm việc độc lập; readiness không cần đợi một lần liveness thành công. Xem [mô hình probe của Kubernetes](https://kubernetes.io/docs/concepts/workloads/pods/probes/).

Hãy gắn mỗi tín hiệu với **hành động sửa lỗi mong muốn**. Khởi động lại giúp xử lý một trạng thái nội bộ hỏng không tự phục hồi. Ngừng nhận lưu lượng phù hợp với một bản chạy cần thời gian hồi phục. Cho thêm thời gian khởi tạo giải quyết một ứng dụng khởi động chậm nhưng vẫn đang tiến triển.

## 2. Spring Boot cung cấp tín hiệu; Kubernetes thực hiện hành động

Luồng trách nhiệm khi dùng HTTP probe:

```text
Trạng thái ứng dụng / phép kiểm tra sức khỏe
    -> Actuator trả HTTP status tại endpoint
    -> kubelet gọi endpoint theo cấu hình probe
    -> kubelet áp dụng ngưỡng thành công/thất bại
    -> cập nhật readiness hoặc dừng container
```

Spring Boot quản lý hai trạng thái qua `ApplicationAvailability`:

- `LivenessState.CORRECT`: trạng thái bên trong được coi là đúng.
- `LivenessState.BROKEN`: trạng thái bên trong hỏng, cần hạ tầng khởi động lại.
- `ReadinessState.ACCEPTING_TRAFFIC`: sẵn sàng nhận lưu lượng.
- `ReadinessState.REFUSING_TRAFFIC`: tạm thời không nên nhận lưu lượng.

Ý nghĩa liveness được định nghĩa trong [API LivenessState](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/LivenessState.html); [ReadinessStateHealthIndicator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/availability/ReadinessStateHealthIndicator.html) đọc trạng thái readiness để tạo kết quả health.

Actuator **không tự khởi động lại JVM** khi báo lỗi. Việc gọi endpoint bằng `curl` trên máy cá nhân cũng không tạo ra cơ chế điều phối của Kubernetes. Tương tự, phát trạng thái `REFUSING_TRAFFIC` không tự dựng một bộ lọc chặn mọi HTTP request. Nó cung cấp tín hiệu để bộ điều phối ngừng gửi yêu cầu mới tới bản chạy.

Liveness mặc định cũng không phải bộ phát hiện mọi lỗi Java: không tự chứng minh toàn bộ luồng nghiệp vụ đúng, mọi khóa đều thông thoáng hay mọi yêu cầu đều thành công. Một sự cố chỉ tác động probe khi nó được phản ánh vào trạng thái/health hoặc làm phép gọi probe thất bại.

## 3. Mối liên hệ với quá trình khởi động

Spring Boot phân biệt khởi tạo context và hoàn tất các tác vụ khởi động. Ứng dụng có thể có liveness đúng trong khi readiness vẫn từ chối lưu lượng. Readiness chuyển sang chấp nhận lưu lượng sau khi các `ApplicationRunner` và `CommandLineRunner` đã được gọi xong. Xem [Application Availability của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability).

Ví dụ tự xây dựng: một dịch vụ cần nạp bảng quy đổi trước khi tính giá.

```text
Container mới chạy
  |
  +-- JVM và Spring context đang khởi tạo
  |     Endpoint có thể chưa truy cập được
  |
  +-- Context đã sẵn sàng, runner đang nạp bảng quy đổi
  |     Liveness có thể UP; readiness vẫn OUT_OF_SERVICE
  |
  +-- Runner hoàn tất
        Readiness chuyển sang UP
        Pod có thể được Service chọn khi các điều kiện Ready khác cũng đạt
```

Không suy ra thời điểm mở cổng chỉ từ một enum trong bộ nhớ. Phép HTTP còn phụ thuộc máy chủ web, cổng, đường dẫn, mạng và cấu hình bảo mật. Cũng không suy ra ứng dụng đã sẵn sàng chỉ từ một dòng log có chữ `Started`.

Nếu tác vụ bắt buộc chạy bất đồng bộ và runner kết thúc trước tác vụ đó, thời điểm runner trả về không còn đại diện cho hoàn tất khởi tạo. Khi thiết kế như vậy, cần một phép kiểm tra readiness thể hiện đúng điều kiện hoàn tất; tránh để tín hiệu sẵn sàng xuất hiện quá sớm.

### Startup probe không phải endpoint `/actuator/startup`

`startupProbe` là trường trong cấu hình Kubernetes. Nó cần một phép kiểm tra thích hợp, chẳng hạn gọi liveness hoặc readiness endpoint.

Endpoint Actuator `/actuator/startup` phục vụ thông tin các bước khởi động khi cấu hình thu thập tương ứng; nó không phải endpoint startup probe mặc định. Đừng chọn đường dẫn chỉ vì tên có chữ `startup`. Tham khảo [danh sách Actuator endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Hai lựa chọn có mục đích khác nhau:

| Startup probe gọi | Mốc được chọn | Hệ quả trong ví dụ nạp bảng quy đổi |
| --- | --- | --- |
| `/actuator/health/liveness` | Ứng dụng đã có thể trả lời tín hiệu liveness thành công | Startup có thể kết thúc trước khi nạp xong; readiness tiếp tục giữ Pod ngoài lưu lượng |
| `/actuator/health/readiness` | Ứng dụng đã đạt điều kiện readiness đang cấu hình | Ngân sách startup phải bao phủ cả giai đoạn nạp bảng; nếu readiness phụ thuộc hệ thống ngoài, sự cố hệ thống đó cũng có thể làm startup hết ngân sách |

Bảng trên là cách chọn hợp đồng cho ứng dụng cụ thể. Không có yêu cầu chung rằng startup luôn phải gọi một trong hai đường dẫn này. Trong ví dụ phía dưới, startup gọi liveness và việc nạp dữ liệu được bảo vệ bằng readiness.

## 4. Thí nghiệm Spring Boot chạy được trên máy cá nhân

Ví dụ độc lập dùng Java 17 trở lên và Spring Boot 3.3.13. Cần Maven, cổng 8080 trống và khả năng tải các dependency. Đây là dự án thí nghiệm tối thiểu, không yêu cầu thêm endpoint vào một module chỉ để có API.

Tạo đúng ba tệp:

```text
probe-demo/
├── pom.xml
└── src/main/
    ├── java/example/probes/ProbeDemoApplication.java
    └── resources/application.yml
```

### 4.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>probe-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
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

### 4.2. `src/main/resources/application.yml`

```yaml
server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true

demo:
  startup-delay-ms: 30000
```

`probes.enabled=true` giúp bật nhóm probe ngay cả khi chạy ngoài Kubernetes. Ví dụ chỉ dùng cổng ứng dụng 8080, không đặt `management.server.port` riêng.

### 4.3. `src/main/java/example/probes/ProbeDemoApplication.java`

```java
package example.probes;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ProbeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProbeDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner warmUp(
            @Value("${demo.startup-delay-ms:30000}") long delayMillis) {
        return args -> Thread.sleep(delayMillis);
    }

    @RestController
    static class HelloController {
        @GetMapping("/hello")
        String hello() {
            return "hello\n";
        }
    }

    @RestController
    @Profile("probe-lab")
    static class LabController {
        private final ConfigurableApplicationContext context;

        LabController(ConfigurableApplicationContext context) {
            this.context = context;
        }

        @PostMapping("/lab/refuse")
        String refuse() {
            AvailabilityChangeEvent.publish(
                    context, ReadinessState.REFUSING_TRAFFIC);
            return "REFUSING_TRAFFIC\n";
        }

        @PostMapping("/lab/accept")
        String accept() {
            AvailabilityChangeEvent.publish(
                    context, ReadinessState.ACCEPTING_TRAFFIC);
            return "ACCEPTING_TRAFFIC\n";
        }

        @PostMapping("/lab/break")
        String breakLiveness() {
            AvailabilityChangeEvent.publish(context, LivenessState.BROKEN);
            return "BROKEN\n";
        }
    }
}
```

`Thread.sleep` chỉ mô phỏng việc nạp dữ liệu bắt buộc; không phải khuyến nghị thêm thời gian chờ vào ứng dụng thực tế. Các route `/lab/*` chỉ phục vụ thí nghiệm, chỉ có khi bật profile `probe-lab`. Chạy thí nghiệm trên địa chỉ loopback như lệnh dưới; không bật các route điều khiển này trên bản triển khai thật.

### 4.4. Build và quan sát quá trình khởi động

Tại thư mục `probe-demo`, mở terminal thứ nhất:

```shell
mvn -q -DskipTests package
java -jar target/probe-demo-1.0.0.jar --spring.profiles.active=probe-lab --server.address=127.0.0.1
```

Dự án dùng dependency của Spring, nên lệnh build Maven chuẩn bị classpath và tạo JAR; không chạy riêng `javac ProbeDemoApplication.java` khi chưa cung cấp dependency.

Trong terminal thứ hai, dùng `curl` hoặc `curl.exe` trên Windows:

```shell
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health/liveness
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health/readiness
```

Hai lệnh trên dùng `/dev/null` của shell POSIX; khi chạy PowerShell với `curl.exe`, thay `/dev/null` bằng `NUL`. Các lệnh `curl -i` phía dưới dùng được mà không cần đổi đường dẫn tệp.

Khi máy chủ đã phục vụ được probe nhưng runner vẫn đang chờ, kết quả status lần lượt là:

```text
200
503
```

Nếu gọi quá sớm, kết nối chưa được mở và `curl` có thể in `000` cùng lỗi kết nối; đó không phải HTTP status 000 do Spring trả về. Nếu gọi sau khi runner hoàn tất thì cả hai là `200`. Khoảng quan sát phụ thuộc thời gian khởi động máy, không được đồng nhất với một mốc đồng hồ tuyệt đối.

Sau khi runner hoàn tất:

```shell
curl -i http://127.0.0.1:8080/actuator/health/liveness
curl -i http://127.0.0.1:8080/actuator/health/readiness
```

Với cấu hình trên, cả hai có HTTP status `200` và body:

```json
{"status":"UP"}
```

Header ngày giờ, thứ tự header và header khác phụ thuộc lần chạy; không cần giống nhau để kết luận trạng thái.

### 4.5. Readiness thất bại nhưng tiến trình vẫn chạy

Chỉ thực hiện sau khi ứng dụng đã sẵn sàng:

```shell
curl -s -X POST http://127.0.0.1:8080/lab/refuse
curl -i http://127.0.0.1:8080/actuator/health/readiness
curl -i http://127.0.0.1:8080/actuator/health/liveness
curl -s http://127.0.0.1:8080/hello
```

Kết quả cần đối chiếu:

| Lệnh | Kết quả |
| --- | --- |
| POST `/lab/refuse` | Body `REFUSING_TRAFFIC` và một ký tự xuống dòng |
| GET readiness | HTTP `503`, body `{"status":"OUT_OF_SERVICE"}` |
| GET liveness | HTTP `200`, body `{"status":"UP"}` |
| GET trực tiếp `/hello` | Body `hello` và một ký tự xuống dòng |

Đây là bằng chứng rằng readiness và liveness có thể khác nhau. Việc `/hello` còn trả lời cũng cho thấy readiness là tín hiệu điều phối: gọi thẳng địa chỉ ứng dụng vẫn có thể vào được. Khi triển khai Kubernetes, Service cần thời gian nhận thay đổi trạng thái; kết nối đang tồn tại và đường truy cập bỏ qua Service cần được xét riêng.

Khôi phục rồi kiểm tra lại:

```shell
curl -s -X POST http://127.0.0.1:8080/lab/accept
curl -i http://127.0.0.1:8080/actuator/health/readiness
```

POST trả `ACCEPTING_TRAFFIC` kèm xuống dòng; readiness trở về HTTP `200`, body `{"status":"UP"}`.

### 4.6. Liveness thất bại không làm JAR tự thoát

Thực hiện sau khi đã khôi phục readiness:

```shell
curl -s -X POST http://127.0.0.1:8080/lab/break
curl -i http://127.0.0.1:8080/actuator/health/liveness
curl -i http://127.0.0.1:8080/actuator/health/readiness
```

POST trả `BROKEN` kèm xuống dòng. Liveness trả HTTP `503` với body `{"status":"DOWN"}`. Trong thí nghiệm này readiness vẫn trả HTTP `200` với body `{"status":"UP"}` vì chỉ trạng thái liveness được đổi, hai nhóm không tự gộp vào nhau. Đây là minh họa tính độc lập, không phải thiết kế khôi phục hoàn chỉnh cho ứng dụng nghiệp vụ.

JAR vẫn chạy trên máy cá nhân. Trên Kubernetes có liveness probe tương ứng, kubelet mới quan sát lỗi đủ ngưỡng và dừng container. Kết thúc thí nghiệm bằng `Ctrl+C`.

## 5. Ghép ba probe trong cấu hình container

Đoạn YAML sau là **fragment của một container** trong `spec.template.spec.containers` của Deployment. Nó không phải manifest đầy đủ để chạy `kubectl apply`. Container đã có image ứng dụng ở trên, lắng nghe cổng 8080 trên địa chỉ Pod và không bật profile `probe-lab`.

```yaml
ports:
  - name: http
    containerPort: 8080

startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 36
  successThreshold: 1

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
  successThreshold: 1

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 2
  successThreshold: 1
```

Không mang `--server.address=127.0.0.1` từ lệnh chạy local vào container này: kubelet phải truy cập được cổng trên địa chỉ Pod.

Đọc cấu hình theo tình huống:

1. **Đang mở JVM/context:** startup probe có ngân sách thiết kế khoảng `36 × 5 = 180` giây. Liveness và readiness chưa bắt đầu.
2. **Liveness endpoint thành công lần đầu:** startup probe kết thúc. Hai probe còn lại bắt đầu hoạt động theo cấu hình của chúng.
3. **Runner còn nạp bảng:** readiness thất bại nên ứng dụng chưa nhận lưu lượng qua cơ chế chọn endpoint sẵn sàng của Service.
4. **Runner hoàn tất:** readiness thành công; Pod có thể trở thành Ready khi những điều kiện khác cũng thỏa mãn.
5. **Về sau readiness lỗi đủ ngưỡng:** bản chạy tạm ra khỏi tập phục vụ, vẫn có cơ hội tự hồi phục.
6. **Về sau liveness lỗi ba lần liên tiếp:** kubelet dừng container; với Deployment, chính sách khởi động lại thông thường là `Always`.

Trong lựa chọn này, 180 giây là ngân sách đến **mốc liveness thành công**, không bảo đảm runner kết thúc trong 180 giây. Nếu yêu cầu vận hành là buộc hoàn tất toàn bộ khởi tạo trong một ngân sách, phải chọn phép startup thể hiện mốc đó và cân nhắc việc nó có phụ thuộc hệ thống ngoài hay không.

Các phép nhân là ước lượng để chọn cấu hình, không phải cam kết thời điểm dừng chính xác. Pha của lần kiểm tra, thời gian chờ, lập lịch và thời gian kết thúc container đều ảnh hưởng thời điểm thực tế. Xem [cách bảo vệ container khởi động chậm](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/#protect-slow-starting-containers-with-startup-probes).

### Ý nghĩa các tham số

| Tham số | Cách dùng |
| --- | --- |
| `periodSeconds` | Chu kỳ kiểm tra; readiness có thể được kiểm tra thường hơn khi Pod chưa Ready |
| `timeoutSeconds` | Thời gian tối đa chờ một lần kiểm tra; cần đủ cho đáp ứng bình thường nhưng không kéo dài vô hạn |
| `failureThreshold` | Số lần thất bại liên tiếp để coi probe đã thất bại |
| `successThreshold` | Số lần thành công liên tiếp để phục hồi; startup và liveness bắt buộc là 1 |
| `initialDelaySeconds` | Độ trễ trước lần kiểm tra đầu; khi có startup probe, độ trễ của liveness/readiness được tính sau khi startup thành công |

Với ví dụ, readiness dùng hai lần lỗi để hạn chế phản ứng với một lỗi thoáng qua. Liveness dùng chu kỳ dài hơn và ba lần lỗi để tránh khởi động lại vì một khoảng chậm ngắn. Đây là các giá trị minh họa; cần chọn từ thời gian khởi động và độ trễ đã đo của ứng dụng.

Nếu tăng `initialDelaySeconds` của liveness rất lớn để chữa khởi động chậm, cùng độ trễ đó cũng làm chậm phát hiện lỗi ở những lần container khởi động sau. Startup probe cho phép tách ngân sách khởi tạo khỏi nhịp liveness khi ứng dụng đã chạy.

## 6. Chọn nội dung kiểm tra theo tình huống

Giả sử có ba bản chạy của dịch vụ tính giá và một cơ sở dữ liệu dùng chung.

### 6.1. Không gắn cơ sở dữ liệu dùng chung vào liveness

Nếu cơ sở dữ liệu ngừng hoạt động mà mỗi bản chạy đều báo liveness hỏng, cả ba sẽ bị khởi động lại. Việc đó không sửa cơ sở dữ liệu; còn làm mất cache đang có và tạo thêm đợt kết nối khi JVM chạy lại. Vì vậy, quyết định liveness nên phản ánh lỗi bên trong mà khởi động lại có khả năng xử lý.

### 6.2. Readiness cần thể hiện khả năng phục vụ đã cam kết

Xét hai thiết kế cụ thể:

- Dịch vụ tính giá chỉ có thể làm việc khi có dữ liệu từ cơ sở dữ liệu: đưa một kiểm tra phụ thuộc thật sự thiết yếu vào readiness có thể phù hợp, nhưng phải chấp nhận tất cả bản chạy có thể cùng mất readiness.
- Dịch vụ vẫn trả kết quả hợp lệ từ dữ liệu cache với thời hạn đã quy định: mất kết nối database không nhất thiết phải khiến bản chạy rời tập phục vụ. Hãy kiểm tra điều kiện phục vụ thực tế thay vì coi mọi phụ thuộc đều bắt buộc.

Các nhóm liveness/readiness mặc định không tự thêm mọi health indicator như database. Khi chủ động mở rộng readiness, có thể cấu hình `management.endpoint.health.group.readiness.include=readinessState,db` **chỉ khi** indicator `db` thực sự tồn tại và chính sách ứng dụng cần nó. Không chép cấu hình này vào dự án thí nghiệm không có DataSource. Xem [kiểm tra trạng thái bên ngoài trong probe](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes.external-state).

`/actuator/health` là kết quả health tổng hợp. Dùng cùng đường dẫn đó cho cả startup, liveness và readiness sẽ khiến ba hành động khác nhau dựa vào một tập điều kiện chung, có thể gồm cả phụ thuộc bên ngoài. Hai nhóm chuyên biệt giúp biểu đạt quyết định chính xác hơn.

## 7. Cổng, mã HTTP và quyền truy cập đều thuộc hợp đồng probe

### Kiểm tra trên đúng đường phục vụ

Nếu đặt management port riêng, probe có thể thành công trên cổng quản trị trong khi cổng nghiệp vụ không còn nhận kết nối. Spring Boot 3.3 hỗ trợ thêm đường dẫn trên cổng ứng dụng:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
```

Khi đó có `/livez` và `/readyz` trên cổng chính. Nếu chọn cách này, hãy đổi `httpGet.path` và cổng trong manifest tương ứng. Đoạn YAML này là phương án bổ sung, không phải một tệp cấu hình khác của thí nghiệm. Tham khảo [cấu hình Kubernetes probe của Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

### Mã HTTP phải phản ánh được thất bại

Trong cấu hình mặc định của thí nghiệm, health `UP` trả 200; `DOWN` và `OUT_OF_SERVICE` trả 503. Với HTTP probe, kubelet đánh giá mã HTTP, không đọc chuỗi `status` trong JSON để suy ra lỗi. Endpoint trả `200` cùng JSON nói rằng lỗi sẽ tạo ra kết luận sai ở phía kubelet.

Kubernetes coi các mã HTTP từ 200 đến dưới 400 là thành công; do đó đường dẫn chuyển hướng tới trang đăng nhập có thể che mất điều kiện cần kiểm tra. Kiểm tra trực tiếp status và đường dẫn thay vì chỉ thấy một trang HTML trả về. Xem [HTTP liveness probe](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/#define-a-liveness-http-request).

Nếu có Spring Security, phải cấu hình cho kubelet truy cập đúng các endpoint probe cần thiết. Bật exposure chỉ làm endpoint có mặt, không tự cấp quyền trong mọi cấu hình SecurityFilterChain. Không mở toàn bộ Actuator chỉ để chữa lỗi 401/403 của probe. Ví dụ độc lập không thêm dependency Spring Security nên không cần tài khoản cho các lệnh thí nghiệm.

## 8. Chẩn đoán bằng bằng chứng

Trên cụm thử nghiệm đã có Deployment thật, dùng các lệnh sau để quan sát, không cần tạo lỗi trên hệ thống đang phục vụ:

```shell
kubectl get pods
kubectl get endpointslices
kubectl get events --sort-by=.metadata.creationTimestamp
```

Dùng tên Pod thực tế từ kết quả để xem `kubectl describe pod` và `kubectl logs --previous` khi cần. Không có một stdout cố định cho các lệnh này vì tên Pod, thời điểm và số lần chạy lại phụ thuộc cụm.

| Dấu hiệu | Câu hỏi cần kiểm tra |
| --- | --- |
| Pod `Running` nhưng chưa Ready | Startup đã thành công chưa; readiness đang lỗi HTTP, timeout hay đúng là đang khởi tạo? |
| `RESTARTS` tăng kèm sự kiện liveness/startup thất bại | Đường dẫn/cổng có đúng; ngân sách có đủ; kiểm tra có vô tình phụ thuộc hệ thống dùng chung không? |
| `RESTARTS` tăng nhưng không có sự kiện probe tương ứng | Kiểm tra exit code, OOMKilled và log lần chạy trước; không quy mọi lần khởi động lại cho liveness |
| Readiness 503, liveness 200 | Có thể là trạng thái tạm thời hợp lệ; xác minh điều kiện phục vụ và thời gian hồi phục |
| Cả hai endpoint 200 nhưng API nghiệp vụ lỗi | Probe chưa bao phủ lỗi đó; phân tích thêm metric, log và yêu cầu nghiệp vụ |
| Readiness dao động liên tục | Kiểm tra ngưỡng, độ trễ, giới hạn tài nguyên và chi phí của chính phép kiểm tra |

Probe nên nhanh, giới hạn thời gian rõ ràng và không gây tác dụng phụ. Mỗi lần kiểm tra không nên nạp lại toàn bộ cache hoặc thực hiện giao dịch ghi. Khi có nhiều replica, chi phí kiểm tra nhân lên theo số bản chạy và tần suất gọi.

## 9. Tự kiểm tra quyết định thiết kế

1. **Context đã chạy nhưng đang nạp bảng quy đổi 45 giây. Có nên báo liveness hỏng?** Không chỉ vì chưa nạp xong. Readiness cần giữ trạng thái chưa sẵn sàng; ngân sách startup cần phù hợp với mốc khởi tạo được chọn.
2. **Một bản chạy tạm thời không đủ khả năng nhận thêm việc nhưng có cơ chế tự hồi phục. Chọn hành động nào?** Ngừng đưa lưu lượng mới tới bản chạy thường phù hợp hơn khởi động lại ngay. Cần có điều kiện rõ ràng để readiness trở lại, tránh dao động đồng loạt khi quá tải.
3. **Database dùng chung lỗi 20 giây. Vì sao restart cả ba JVM có thể làm tình hình xấu hơn?** Restart không sửa database, làm mất trạng thái hữu ích và tạo thêm áp lực kết nối khi các bản chạy cùng lên lại.
4. **Startup gọi liveness thành công sau 8 giây, runner hoàn tất sau 40 giây. Có nhận lưu lượng ngay giây thứ 8 không?** Không nếu readiness vẫn thất bại và đường truy cập đi qua cơ chế Service tôn trọng readiness. Startup kết thúc không thay thế điều kiện Ready.
5. **Readiness đã trả 503 nhưng gọi trực tiếp `/hello` vẫn được. Có mâu thuẫn không?** Không. Trạng thái readiness cung cấp tín hiệu điều phối; muốn chặn xử lý tại ứng dụng cần cơ chế riêng.
6. **Có thể dùng một endpoint luôn trả 200 cho cả ba probe không?** Endpoint đó chỉ chứng minh một yêu cầu đơn giản còn được trả lời. Nó không thể hiện việc khởi tạo hoàn tất hay điều kiện sẵn sàng nghiệp vụ; phải chọn phép kiểm tra phù hợp với từng quyết định.

Khi giải thích một cấu hình probe, hãy chỉ ra được: **điều kiện được kiểm tra → endpoint/mã HTTP → ngưỡng quan sát → hành động của kubelet → cách bản chạy trở lại phục vụ**. Chuỗi này giúp đánh giá cả tính đúng của tín hiệu lẫn hậu quả của cấu hình.

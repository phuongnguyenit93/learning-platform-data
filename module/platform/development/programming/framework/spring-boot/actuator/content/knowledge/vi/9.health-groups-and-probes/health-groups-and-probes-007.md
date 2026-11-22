# Thiết lập endpoint health/liveness và health/readiness cho hạ tầng

## 1. Từ trạng thái ứng dụng đến quyết định của hạ tầng

Một tiến trình Java còn chạy chưa chắc đã nhận được yêu cầu. Ngược lại, một ứng dụng đang tạm ngừng nhận yêu cầu chưa chắc cần khởi động lại. Khi triển khai nhiều bản sao, hạ tầng cần hai tín hiệu riêng để chọn đúng hành động.

| Tín hiệu | Câu hỏi cần trả lời | Hành động khi kiểm tra thất bại đủ ngưỡng |
| --- | --- | --- |
| Sự sống (liveness) | Bản sao này còn ở trạng thái nội bộ có thể hoạt động hoặc tự phục hồi không? | Kubernetes khởi động lại container theo chính sách áp dụng. |
| Sự sẵn sàng (readiness) | Bản sao này đã sẵn sàng nhận yêu cầu mới chưa? | Kubernetes đánh dấu chưa sẵn sàng để loại khỏi luồng phân phối thông thường của Service; container vẫn chạy. |
| Khởi động (startup) | Ứng dụng đã vượt qua giai đoạn khởi động được cho phép chưa? | Nếu hết ngưỡng mà vẫn thất bại, container bị khởi động lại. |

Probe là phép thăm dò do hạ tầng thực hiện định kỳ. Endpoint là địa chỉ HTTP ứng dụng cung cấp cho phép thăm dò đó. Spring Boot tạo tín hiệu; kubelet đọc tín hiệu và thực hiện chính sách. Chỉ bật endpoint không làm hạ tầng tự biết phải gọi địa chỉ nào.

Ví dụ: dịch vụ đã tạo xong Spring context nhưng còn nạp dữ liệu khởi động. Nó có thể còn sống trong khi chưa sẵn sàng nhận khách. Nếu dùng cùng một phép kiểm tra cho hai mục đích, hạ tầng có thể khởi động lại liên tục một ứng dụng vốn chỉ cần thêm thời gian.

Ba loại probe và hành động tương ứng được mô tả trong [tài liệu Kubernetes](https://kubernetes.io/docs/concepts/workloads/pods/probes/). Bài này dùng Spring Boot 3.3.x, Java 21 và HTTP thông thường; không giả định ứng dụng đã có Spring Security.

## 2. Spring Boot cung cấp những địa chỉ nào?

Khi các nhóm probe được bật, với đường dẫn và cổng mặc định:

| Địa chỉ | Ý nghĩa |
| --- | --- |
| `GET /actuator/health` | Sức khỏe tổng hợp; có thể gồm nhiều bộ kiểm tra khác nhau. |
| `GET /actuator/health/liveness` | Nhóm dành cho sự sống. |
| `GET /actuator/health/readiness` | Nhóm dành cho sự sẵn sàng. |

`health` là mã endpoint Actuator; `liveness` và `readiness` là các nhóm health bên dưới. Vì vậy cấu hình HTTP exposure dùng `health`, không dùng danh sách `liveness,readiness`.

Spring Boot tự bật các nhóm probe khi nhận diện môi trường Kubernetes. Để chạy nhất quán cả ở máy cá nhân và môi trường triển khai, bài này khai báo rõ `management.endpoint.health.probes.enabled=true`. Với ánh xạ mặc định, trạng thái `UP` trả HTTP 200; `DOWN` và `OUT_OF_SERVICE` trả HTTP 503. Xem [Spring Boot 3.3: Kubernetes Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

Phần mềm kiểm tra hạ tầng cần dựa vào mã HTTP và lỗi kết nối/timeout. Không chỉ tìm chuỗi `UP` trong JSON. Một proxy trả trang đăng nhập hoặc một bộ điều khiển tự viết luôn trả 200 có thể tạo tín hiệu sai.

## 3. Tạo ứng dụng mẫu có thể chạy

Đây là dự án Gradle độc lập để thực hành, không phải yêu cầu sửa cấu hình build của một module đang có. Dùng Java 21 và Gradle 8.5. Phiên bản Spring Boot 3.3.0 dưới đây được cố định cho ví dụ tái lập trong dòng 3.3; khi tích hợp vào dự án thật, giữ phiên bản 3.3.x do dự án quản lý.

### 3.1. Khai báo build

Tệp `settings.gradle`: 

```groovy
rootProject.name = 'probe-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

`spring-boot-starter-web` cung cấp máy chủ HTTP; `spring-boot-starter-actuator` cung cấp health endpoint. BOM quản lý phiên bản thư viện phụ thuộc. Không cần tự viết controller cho `/actuator/health/liveness` hoặc `/actuator/health/readiness`.

### 3.2. Lớp chạy và công cụ thay đổi readiness trong phòng thực hành

Tệp `src/main/java/example/probes/ProbeDemo.java`:

```java
package example.probes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ProbeDemo {
    public static void main(String[] args) {
        SpringApplication.run(ProbeDemo.class, args);
    }

    @RestController
    @Profile("probe-lab")
    @RequestMapping("/lab/readiness")
    static class ReadinessLabController {
        private final ApplicationContext context;

        ReadinessLabController(ApplicationContext context) {
            this.context = context;
        }

        @PostMapping("/refuse")
        String refuse() {
            AvailabilityChangeEvent.publish(context, ReadinessState.REFUSING_TRAFFIC);
            return "REFUSING_TRAFFIC";
        }

        @PostMapping("/accept")
        String accept() {
            AvailabilityChangeEvent.publish(context, ReadinessState.ACCEPTING_TRAFFIC);
            return "ACCEPTING_TRAFFIC";
        }
    }
}
```

Hai đường dẫn `/lab/readiness/*` là công cụ thí nghiệm, chỉ tồn tại khi bật profile `probe-lab`. Lệnh chạy bên dưới buộc máy chủ nghe trên loopback để công cụ này chỉ dùng từ máy thực hành. Không bật profile đó trong Deployment.

`AvailabilityChangeEvent.publish(...)` thay đổi trạng thái được `ApplicationAvailability` ghi nhận; bộ kiểm tra readiness chuyển trạng thái đó thành phản hồi health. Nó không tự chặn các controller nghiệp vụ. Bởi vậy vẫn có thể gọi `/lab/readiness/accept` trực tiếp sau khi readiness thất bại. API phát sự kiện được định nghĩa tại [AvailabilityChangeEvent](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html).

### 3.3. Cấu hình Actuator

Tệp `src/main/resources/application.yml`:

```yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      show-components: never
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState
```

Ở đây hai nhóm được giới hạn rõ bằng tên bộ kiểm tra `livenessState` và `readinessState`. `show-details` và `show-components` giữ phản hồi gọn, tránh đưa cấu trúc nội bộ ra phép thăm dò. Hai nhóm vẫn được phân biệt bằng URL.

`server.shutdown=graceful` cho phép máy chủ xử lý các yêu cầu đang thực hiện trong thời gian dừng. `timeout-per-shutdown-phase` là thời hạn cho từng pha dừng, không phải cam kết toàn bộ JVM luôn kết thúc trong đúng 20 giây. Xem [Spring Boot 3.3: Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html).

### 3.4. Chạy ứng dụng

Từ thư mục dự án, tạo wrapper một lần nếu chưa có:

```bash
gradle wrapper --gradle-version 8.5
```

Chạy trên Linux/macOS:

```bash
./gradlew bootRun --args='--spring.profiles.active=probe-lab --server.address=127.0.0.1'
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=probe-lab --server.address=127.0.0.1"
```

Chờ ứng dụng khởi động xong. Không dùng `javac ProbeDemo.java` với classpath trống: lớp này cần thư viện Spring và cấu hình tài nguyên do Gradle cung cấp.

## 4. Kiểm chứng thành công và thất bại qua HTTP

Các lệnh sau dùng Bash và `curl`, chạy ở cửa sổ khác. Trong PowerShell có thể dùng `curl.exe` để tránh nhầm với bí danh của lệnh PowerShell. Các output dưới đây giả định đúng cấu hình mẫu, ứng dụng đã sẵn sàng và không có cấu hình ghi đè từ môi trường.

### 4.1. Hai nhóm cùng hoạt động bình thường

```bash
curl -sS -w '\nHTTP %{http_code}\n' http://127.0.0.1:8080/actuator/health/liveness
curl -sS -w '\nHTTP %{http_code}\n' http://127.0.0.1:8080/actuator/health/readiness
```

Output, lần lượt cho mỗi lệnh:

```text
{"status":"UP"}
HTTP 200
{"status":"UP"}
HTTP 200
```

Không cần in toàn bộ header vì ngày giờ, kết nối và các trường khác có thể thay đổi. Phép kiểm tra này xác nhận đường dẫn, mã HTTP và dữ liệu trạng thái.

### 4.2. Tạm rút bản sao khỏi luồng nhận yêu cầu

```bash
curl -sS -X POST -w '\nHTTP %{http_code}\n' http://127.0.0.1:8080/lab/readiness/refuse
curl -sS -w '\nHTTP %{http_code}\n' http://127.0.0.1:8080/actuator/health/readiness
curl -sS -w '\nHTTP %{http_code}\n' http://127.0.0.1:8080/actuator/health/liveness
```

Output:

```text
REFUSING_TRAFFIC
HTTP 200
{"status":"OUT_OF_SERVICE"}
HTTP 503
{"status":"UP"}
HTTP 200
```

HTTP 200 của lệnh POST chỉ cho biết thao tác đổi trạng thái đã thành công. Readiness trả 503 mới là tín hiệu hạ tầng dùng để ngừng phân phối yêu cầu mới. Liveness vẫn 200 vì ứng dụng còn hoạt động; không có lý do khởi động lại chỉ vì thao tác này.

Khôi phục readiness:

```bash
curl -sS -X POST -w '\nHTTP %{http_code}\n' http://127.0.0.1:8080/lab/readiness/accept
curl -sS -w '\nHTTP %{http_code}\n' http://127.0.0.1:8080/actuator/health/readiness
```

Output:

```text
ACCEPTING_TRAFFIC
HTTP 200
{"status":"UP"}
HTTP 200
```

Trên máy cá nhân, không có kubelet nên HTTP 503 không làm tiến trình bị khởi động lại hoặc mất khả năng nhận kết nối trực tiếp. Khi có Kubernetes, việc rút/đưa lại bản sao vào luồng Service còn phụ thuộc ngưỡng probe và thời gian cập nhật định tuyến.

### 4.3. Tín hiệu thay đổi theo vòng đời

Spring Boot đánh dấu liveness là `CORRECT` sau khi context được làm mới và readiness là `ACCEPTING_TRAFFIC` sau khi các `ApplicationRunner`/`CommandLineRunner` hoàn thành. Trước khi cổng HTTP mở, phép thăm dò có thể gặp lỗi kết nối; không phải giai đoạn nào cũng đọc được một JSON 503. Các tác vụ nạp bắt buộc nên nằm trong phần khởi động có quản lý; một tác vụ bất đồng bộ tự tạo có thể vẫn đang chạy khi Boot đã công bố sẵn sàng. Xem [Spring Boot 3.3: Application Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability).

Probe mặc định không phải máy phát hiện mọi deadlock, mọi lỗi nghiệp vụ hay mọi trường hợp cạn tài nguyên. Một phản hồi 200 chỉ chứng minh phép kiểm tra được chọn đã thành công ở thời điểm đó. Vẫn cần log, số liệu vận hành và kiểm tra chức năng độc lập.

## 5. Nối hai endpoint với Kubernetes

Khi dùng chung cổng 8080, cấu hình probe trỏ thẳng vào hai địa chỉ Actuator. Dưới đây là đoạn `spec.template.spec` để ghép vào Deployment hiện có; image `probe-demo:1.0.0` phải được build và đưa vào môi trường cluster trước. Không bật `probe-lab` và không bind `server.address` vào loopback khi chạy container phục vụ hạ tầng.

```yaml
terminationGracePeriodSeconds: 40
containers:
  - name: probe-demo
    image: probe-demo:1.0.0
    ports:
      - name: http
        containerPort: 8080
    startupProbe:
      httpGet:
        path: /actuator/health/liveness
        port: http
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 30
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
      failureThreshold: 3
      successThreshold: 1
```

Đọc đoạn cấu hình theo thứ tự:

1. `startupProbe` cho phép ngân sách khởi động xấp xỉ `30 × 5 = 150` giây. Trong lúc startup chưa thành công, kubelet chưa thực hiện liveness/readiness. Đây là ngân sách thiết kế gần đúng; không phải đồng hồ cam kết chính xác đến từng giây.
2. Startup dùng liveness. Nó có thể thành công trước khi các tác vụ khởi động nghiệp vụ hoàn tất; readiness vẫn ngăn Service gửi yêu cầu quá sớm. Nếu tác vụ sau khi context đã khởi động có thể treo vĩnh viễn, cần cơ chế giới hạn thời gian hoặc báo lỗi cho tác vụ đó.
3. Liveness chạy định kỳ; ba lần thất bại liên tiếp đạt ngưỡng khởi động lại. Không dùng độ trễ khởi động thật lớn để che lỗi liveness trong suốt vòng đời.
4. Readiness chạy độc lập sau startup. Thất bại đủ ngưỡng làm bản sao không sẵn sàng; khi hồi phục đủ `successThreshold`, nó có thể nhận yêu cầu lại.
5. `terminationGracePeriodSeconds` phải đủ cho quá trình dừng thực tế, bao gồm công việc khác ngoài xử lý HTTP. Con số 40 giây chỉ là cấu hình mẫu cần đo lại.

Các trường ngưỡng, chu kỳ và timeout được định nghĩa trong [hướng dẫn cấu hình probe của Kubernetes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/). Chọn giá trị từ thời gian khởi động và độ trễ đã đo dưới tải; timeout quá gắt có thể biến một đợt CPU bận ngắn thành nhiều lần khởi động lại.

Kubelet thường gọi trực tiếp IP của Pod và cổng container, không đi qua tên miền Ingress. `containerPort` đặt tên cổng để tham chiếu, không tự mở một máy chủ HTTP. Nếu ứng dụng chỉ nghe tại `127.0.0.1` trong container, việc gọi từ node đến IP Pod có thể thất bại.

## 6. Nếu Actuator chạy trên cổng quản trị riêng

Giả sử API phục vụ khách trên 8080, còn Actuator trên 9090. Nếu kubelet chỉ kiểm tra 9090, cổng quản trị vẫn có thể trả 200 trong khi máy chủ phục vụ khách gặp sự cố. Hãy cung cấp các nhóm probe trên cổng chính và cho hạ tầng kiểm tra cổng đó.

Thay khối `management` trong cấu hình trước bằng:

```yaml
management:
  server:
    port: 9090
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      show-components: never
      probes:
        enabled: true
        add-additional-paths: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState
```

Khi đó dùng bản đồ địa chỉ sau:

| Cổng | Đường dẫn | Dùng cho |
| --- | --- | --- |
| 9090 | `/actuator/health/liveness`, `/actuator/health/readiness` | Truy cập Actuator qua cổng quản trị. |
| 8080 | `/livez`, `/readyz` | Probe đi qua máy chủ chính. |

Trong YAML Kubernetes ở phần trước, đổi `startupProbe.httpGet.path` và `livenessProbe.httpGet.path` thành `/livez`; đổi `readinessProbe.httpGet.path` thành `/readyz`; giữ `port: http` là cổng 8080. Không chuyển chúng sang 9090 rồi cho rằng đã kiểm tra được đường nhận kết nối của API chính.

Kiểm tra thủ công:

```bash
curl -sS -w '\nHTTP %{http_code}\n' http://127.0.0.1:8080/livez
curl -sS -w '\nHTTP %{http_code}\n' http://127.0.0.1:8080/readyz
curl -sS -w '\nHTTP %{http_code}\n' http://127.0.0.1:9090/actuator/health/readiness
```

Khi ứng dụng sẵn sàng, mỗi lệnh trả body `{"status":"UP"}` và dòng `HTTP 200`. Các đường dẫn bổ sung này là khả năng của nhóm probe, được mô tả trong [Spring Boot 3.3: probe trên cổng chính](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

Nếu cấu hình context path, base path hoặc quy tắc reverse proxy, cần xác minh URL thật trên cổng mà kubelet gọi. Không ghép đường dẫn từ trí nhớ. `/livez` và `/readyz` trong ví dụ giả định không có context path bổ sung.

## 7. Quyết định bộ kiểm tra nào thuộc từng nhóm

Tránh trỏ cả hai probe vào `/actuator/health`. Giả sử endpoint tổng hợp có bộ kiểm tra cơ sở dữ liệu: một sự cố database có thể làm endpoint tổng hợp thất bại dù tiến trình ứng dụng còn tốt. Nếu dùng nó cho liveness, toàn bộ bản sao có thể cùng bị khởi động lại mà database vẫn không được sửa.

Giữ liveness tập trung vào khả năng hoạt động nội bộ. Đối với readiness, hãy hỏi: khi phụ thuộc này hỏng, bản sao còn phục vụ được một phần chức năng có giá trị không, và việc loại bản sao có giúp chuyển khách sang bản sao tốt hơn không?

| Tình huống thiết kế | Quyết định cần cân nhắc |
| --- | --- |
| Bộ nhớ đệm tùy chọn hỏng nhưng còn đường lấy dữ liệu chính | Để readiness tiếp tục thành công có thể hợp lý nếu hệ thống vẫn phục vụ được. |
| Tài nguyên riêng của một bản sao hỏng và các bản sao khác còn tốt | Readiness thất bại có thể giúp chuyển luồng sang bản sao khác. |
| Database dùng chung ngừng hoạt động, mọi bản sao đều cần nó | Đưa database vào readiness có thể khiến toàn bộ Service không còn bản sao sẵn sàng; phải chọn chính sách có chủ đích. |

Nếu đã quyết định database là điều kiện bắt buộc và ứng dụng thật sự có bộ kiểm tra `db`, có thể thay riêng nhóm readiness bằng đoạn sau:

```yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include:
            - readinessState
            - db
```

Đây là đoạn ghi đè nhóm, không phải toàn bộ `application.yml`. Không áp dụng nguyên đoạn này vào ứng dụng mẫu vốn chưa có DataSource. Một thành viên nhóm không tồn tại có thể khiến kiểm tra cấu hình nhóm thất bại khi khởi động.

Không dùng `include: '*'` chỉ để khỏi phải quyết định thành viên. Với bộ kiểm tra tự viết, thao tác kiểm tra phải nhẹ, có giới hạn thời gian và không tạo tác dụng phụ như ghi dữ liệu nghiệp vụ. Một endpoint readiness gây quá tải database theo mỗi lần probe đang làm hệ thống yếu thêm.

## 8. Mã HTTP, bảo mật và đường mạng

Kubernetes HTTP probe xem mã 200–399 là thành công; JSON không được dùng để suy luận trạng thái nghiệp vụ. Vì vậy phải tránh chuyển hướng sang trang đăng nhập: chuỗi chuyển hướng có thể làm kết quả kiểm tra khác kỳ vọng. Giữ phản hồi probe trực tiếp và kiểm chứng từ đúng đường mạng triển khai. Xem [quy tắc HTTP probe](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

Ứng dụng mẫu không thêm Spring Security. Nếu dự án đã có `SecurityFilterChain`, quy tắc bảo mật hiện hữu có thể trả 401/403 hoặc redirect trước khi health được xử lý. Khi tích hợp:

- Cho phép đúng phương thức GET và đúng địa chỉ probe mà hạ tầng cần, gồm `/livez` và `/readyz` nếu đang dùng.
- Giữ nguyên quy tắc xác thực/phân quyền của API nghiệp vụ và các endpoint quản trị còn lại; không mở toàn bộ `/actuator/**` chỉ để probe chạy.
- Kiểm tra luật mạng, sidecar và cấu hình cổng để node có thể thăm dò Pod; không suy ra việc truy cập được từ laptop đồng nghĩa kubelet truy cập được.
- Không đưa mật khẩu hoặc token dài hạn vào đường dẫn probe. Phản hồi chỉ cần mã HTTP và trạng thái tối thiểu.

`show-details: never` không phải cơ chế xác thực. Cổng quản trị riêng cũng không tự tạo ranh giới mạng an toàn. Chính sách mạng và chính sách truy cập phải được cấu hình theo môi trường.

Nếu đã tùy biến `management.endpoint.health.status.http-mapping`, hãy kiểm tra lại bằng tình huống thất bại. Một trạng thái lỗi bị ánh xạ thành 200 sẽ làm hạ tầng giữ bản sao trong luồng. Khi khai báo ánh xạ tùy chỉnh, cần lưu ý việc giữ các ánh xạ lỗi mặc định theo hợp đồng của phiên bản Boot đang dùng.

## 9. Chẩn đoán theo triệu chứng

| Triệu chứng | Kiểm tra trước |
| --- | --- |
| `/actuator/health` có dữ liệu nhưng `/liveness` hoặc `/readiness` trả 404 | Probe đã bật chưa; URL có đủ `/actuator/health/` không; có đổi base path không. |
| 401, 403 hoặc chuyển hướng | Quy tắc Spring Security, xác thực proxy và đường dẫn bổ sung trên cổng chính. |
| `Connection refused` | Tiến trình đã mở cổng chưa; sai cổng hay địa chỉ bind; đang gọi cổng chính hay quản trị. |
| 503 với `OUT_OF_SERVICE` ở readiness | Trạng thái đã sẵn sàng chưa; công cụ thực hành có đang để `REFUSING_TRAFFIC`; thành viên bổ sung nào thất bại. |
| Bản sao bị khởi động lại liên tục | Sự kiện probe, startup budget, CPU/timeout, liveness có vô tình phụ thuộc hệ thống bên ngoài không. |
| Management 9090 thành công nhưng API 8080 lỗi | Probe có đang đi qua cổng chính bằng `/livez` và `/readyz` không. |
| Không thể khởi động sau khi thêm thành viên nhóm | Tên bộ kiểm tra có tồn tại trong cấu hình/dependency hiện tại không. |

Khi Deployment thật đã tồn tại, dùng các lệnh sau để xem trạng thái và sự kiện; thay lựa chọn nhãn bằng nhãn thực tế nếu tên ứng dụng khác:

```bash
kubectl get pods -l app=probe-demo
kubectl describe pods -l app=probe-demo
kubectl logs -l app=probe-demo --all-containers=true --tail=100
```

Phân biệt `Running` với `Ready`: container có thể đang chạy nhưng chưa sẵn sàng nhận yêu cầu. Đọc cả số lần khởi động lại và thông báo probe. Không chỉ tăng timeout trước khi xác minh mã HTTP, cổng và địa chỉ.

## 10. Thực hành xác nhận hợp đồng với hạ tầng

1. Chạy mẫu với profile `probe-lab`. Ghi lại mã HTTP và body của hai nhóm lúc bình thường.
2. Gọi thao tác `refuse`; xác nhận readiness là 503 trong khi liveness vẫn là 200. Giải thích vì sao tiến trình Java vẫn chạy và vì sao vẫn gọi được trực tiếp thao tác `accept`.
3. Gọi `accept`; xác nhận readiness trở lại 200 mà không phải khởi động lại.
4. Tắt ứng dụng, chuyển sang cấu hình management 9090 rồi chạy lại. Kiểm tra cả hai địa chỉ Actuator và hai đường dẫn trên 8080.
5. Trên môi trường Kubernetes thực hành, dùng đúng đường dẫn/cổng đã chọn, quan sát `Ready` và số lần restart. Không đưa các công cụ đổi trạng thái của phòng thực hành vào Deployment phục vụ thật.
6. Mô phỏng khởi động chậm có kiểm soát hoặc một lần sai đường dẫn trong môi trường thực hành; đọc sự kiện để phân biệt lỗi startup, lỗi định tuyến HTTP và trạng thái chưa sẵn sàng. Khôi phục cấu hình sau phép thử.

Kết quả cần đạt là một hợp đồng rõ ràng: ứng dụng công bố hai tín hiệu có ý nghĩa khác nhau; hạ tầng gọi đúng địa chỉ, cổng và ngưỡng; phép thử thất bại chứng minh rằng hệ thống rút bản sao hoặc khởi động lại đúng tình huống.

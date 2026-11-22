# Kích hoạt probe trong và ngoài môi trường Kubernetes

## 1. Probe giải quyết vấn đề gì?

Một tiến trình Java còn chạy chưa chắc đã nhận được yêu cầu. Ngược lại, một ứng dụng đang hoàn tất khởi tạo có thể cần thêm thời gian chứ chưa cần bị khởi động lại. Probe là phép kiểm tra định kỳ giúp hạ tầng đưa ra hành động phù hợp với từng tình huống.

Trong Spring Boot Actuator, cần phân biệt hai câu hỏi:

| Phép kiểm tra | Câu hỏi cần trả lời | Ý nghĩa đối với hạ tầng |
| --- | --- | --- |
| Tính sống (liveness) | Trạng thái bên trong có cho phép ứng dụng tiếp tục hoạt động hoặc tự phục hồi không? | Khi thất bại đủ ngưỡng, Kubernetes khởi động lại container theo chính sách của Pod. |
| Tính sẵn sàng (readiness) | Thể hiện ứng dụng này đã sẵn sàng nhận lưu lượng chưa? | Khi chưa sẵn sàng, Kubernetes loại Pod khỏi các đích phục vụ thông thường của Service; riêng readiness thất bại không yêu cầu khởi động lại container. |

Ví dụ, ứng dụng đang chạy bước nạp dữ liệu ban đầu có thể còn sống nhưng chưa sẵn sàng. Đừng dùng cùng một tín hiệu cho cả hai quyết định. Spring Boot cung cấp trạng thái ứng dụng qua `ApplicationAvailability`; Actuator chuyển những trạng thái đó thành kết quả health. [Spring Boot 3.3: Application Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability)

Bài này dùng Spring Boot **3.3.13**, JDK **21**, Spring MVC và Actuator. Các URL giả định ứng dụng dùng HTTP, context path gốc và tiền tố Actuator mặc định. Ví dụ cố ý không thêm Spring Security để tập trung kiểm tra cấu hình probe.

## 2. Phân biệt trạng thái, URL và bộ phận gọi probe

Có ba lớp cần phối hợp:

1. **Trạng thái bên trong:** `ApplicationAvailability` giữ các trạng thái liveness/readiness.
2. **Công bố qua HTTP:** Actuator tạo nhóm health `liveness` và `readiness`, rồi phục vụ tại URL tương ứng.
3. **Kiểm tra và hành động:** kubelet, bộ cân bằng tải hoặc hệ thống giám sát gọi URL và quyết định làm gì khi kiểm tra thất bại.

`AvailabilityProbesAutoConfiguration` là cấu hình tự động tham gia tạo các chỉ báo cùng nhóm probe trong Spring Boot 3.3. Người viết ứng dụng thường chỉ cần cấu hình thuộc tính, không cần tự viết controller trả về `UP`. [API AvailabilityProbesAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/availability/AvailabilityProbesAutoConfiguration.html)

**Bật probe trong Spring Boot không tự tạo `livenessProbe` hay `readinessProbe` trong Pod.** Cần cấu hình cả hai phía. Tương tự, chạy một image bằng Docker không tự biến môi trường đó thành Kubernetes.

## 3. Quy tắc kích hoạt trong Spring Boot 3.3

Thuộc tính chính là:

```properties
management.endpoint.health.probes.enabled=true
```

Với cấu hình tự động thông thường, không có nhóm probe do người dùng tự định nghĩa:

| Môi trường Spring Boot nhận diện | Không đặt thuộc tính probe | Đặt `true` | Đặt `false` |
| --- | --- | --- | --- |
| Kubernetes | Tự kích hoạt hai nhóm probe | Kích hoạt rõ ràng | Tắt cấu hình tự động probe |
| Ngoài Kubernetes: máy cá nhân, VM, Docker thông thường | Không tự kích hoạt hai nhóm probe | Kích hoạt rõ ràng | Không kích hoạt |

Hai URL mặc định sau khi bật là `/actuator/health/liveness` và `/actuator/health/readiness`. Chỉ riêng `/actuator/health` hoạt động không chứng minh hai nhóm probe đã được bật. [Spring Boot 3.3: Kubernetes Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)

Spring Boot nhận diện Kubernetes qua các biến môi trường dạng `*_SERVICE_HOST` và `*_SERVICE_PORT`. Có thể điều chỉnh việc nhận diện bằng `spring.main.cloud-platform`. Tên profile như `k8s`, tên image hay tên thư mục không thay thế cơ chế này. [Spring Boot 3.3: Deploying to Kubernetes](https://docs.spring.io/spring-boot/3.3/how-to/deployment/cloud.html#howto.deployment.cloud.kubernetes)

Nếu mục tiêu chỉ là có probe trên mọi môi trường, đặt `management.endpoint.health.probes.enabled=true` diễn đạt đúng ý định và tránh phụ thuộc vào nhận diện nền tảng.

Cũng cần phân biệt các thuộc tính:

| Thuộc tính | Phạm vi tác động |
| --- | --- |
| `management.endpoint.health.enabled` | Bật/tắt endpoint health. |
| `management.endpoints.web.exposure.include` | Chọn các **ID endpoint** được công bố qua HTTP. Với probe, cần ID `health`. |
| `management.endpoint.health.probes.enabled` | Bật hai nhóm probe do cấu hình tự động cung cấp. |
| `management.endpoint.health.probes.add-additional-paths` | Thêm đường dẫn probe trên cổng ứng dụng chính khi các nhóm probe đã được bật. |

`liveness` và `readiness` là tên nhóm thuộc endpoint `health`; không dùng `include: liveness,readiness` để thay cho `include: health`. Cấu hình công bố qua HTTP cũng không thay thế quy tắc xác thực/phân quyền. [Danh mục thuộc tính Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator)

## 4. Ví dụ hoàn chỉnh chạy ngoài Kubernetes

Tạo một dự án độc lập với cấu trúc:

```text
probe-demo/
├── pom.xml
└── src/main/
    ├── java/demo/ProbeApplication.java
    └── resources/application.yml
```

Nội dung `pom.xml`:

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

    <groupId>demo</groupId>
    <artifactId>probe-demo</artifactId>
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

Nội dung `src/main/java/demo/ProbeApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProbeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProbeApplication.class, args);
    }
}
```

Nội dung `src/main/resources/application.yml`:

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
```

`spring-boot-starter-web` cung cấp máy chủ HTTP; `spring-boot-starter-actuator` cung cấp endpoint quản trị. Việc đặt `include: health` giữ chủ đích công bố rõ ràng; không cần mở toàn bộ endpoint bằng `"*"`.

Từ thư mục dự án, dùng Maven 3.6.3+ và JDK 21:

```shell
mvn package
java -jar target/probe-demo-1.0.0.jar
```

Đây là ứng dụng Spring Boot có thư viện phụ thuộc nên dùng Maven để biên dịch và đóng gói; một lệnh `javac ProbeApplication.java` riêng lẻ sẽ thiếu classpath.

Đợi ứng dụng hoàn tất khởi động, rồi mở terminal khác:

```shell
curl -sS http://localhost:8080/actuator/health/liveness
curl -sS http://localhost:8080/actuator/health/readiness
```

Mỗi yêu cầu trả JSON sau khi trạng thái tương ứng đã tốt; body có thể không có ký tự xuống dòng cuối:

```json
{"status":"UP"}
```

Dùng `curl -i` nếu cần xem cả mã HTTP. Với cấu hình ví dụ, kết quả ổn định sau khởi động là HTTP `200`. Trong lúc khởi động, tùy thời điểm, cổng có thể chưa mở hoặc readiness chưa sẵn sàng; không lấy một lần gọi quá sớm làm kết luận cấu hình bị sai.

## 5. Thí nghiệm bật, tắt và nhận diện nền tảng

Dừng tiến trình trước bằng Ctrl+C rồi chạy từng trường hợp dưới đây. Các đối số đặt **sau** tên JAR là thuộc tính dòng lệnh của Spring Boot và ghi đè cấu hình trong `application.yml`.

### 5.1. Chủ động tắt probe

```shell
java -jar target/probe-demo-1.0.0.jar --management.endpoint.health.probes.enabled=false
```

Sau khi ứng dụng sẵn sàng, trong ví dụ này:

- `/actuator/health` vẫn tồn tại.
- `/actuator/health/liveness` và `/actuator/health/readiness` không còn do cấu hình tự động cung cấp; yêu cầu tới chúng trả `404`.
- Tắt probe không đồng nghĩa tắt máy chủ hay endpoint health.

Kết quả này giả định chưa tự định nghĩa nhóm hoặc controller dùng cùng đường dẫn.

### 5.2. Bật rõ ràng ngoài Kubernetes

```shell
java -jar target/probe-demo-1.0.0.jar --spring.main.cloud-platform=none --management.endpoint.health.probes.enabled=true
```

Hai URL probe vẫn hoạt động. Trường hợp này chứng minh probe không phụ thuộc bắt buộc vào Kubernetes.

### 5.3. Kiểm tra việc tự bật trên Kubernetes

Muốn kiểm chứng **tự bật**, cần bỏ dòng `enabled: true` khỏi `application.yml`, đóng gói lại rồi chạy trong Pod mà Spring Boot nhận diện là Kubernetes. Không giữ thuộc tính `true` rồi kết luận rằng cơ chế nhận diện đã hoạt động.

Có thể dùng lệnh sau để thử nhánh cấu hình nền tảng trên máy cá nhân, sau khi đã bỏ thuộc tính probe và đóng gói lại:

```shell
java -jar target/probe-demo-1.0.0.jar --spring.main.cloud-platform=kubernetes
```

Đây là phép thử **ép nhận diện nền tảng**, không tạo cluster, Pod hay kubelet. Để chỉ bật probe khi chạy bình thường trên máy cá nhân, dùng thuộc tính probe thay vì ép toàn bộ nhận diện nền tảng.

## 6. Cấu hình Kubernetes gọi hai probe

Đoạn YAML sau là **phần cấu hình của một container đã có `name` và `image` trong Pod template**. Ghép các khóa này vào đúng container; đây không phải manifest Deployment hoàn chỉnh. Ứng dụng ví dụ đang nghe cổng `8080`, dùng đường dẫn mặc định và đã bật probe:

```yaml
ports:
  - name: http
    containerPort: 8080

startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 30

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
```

Ý nghĩa các quyết định trong ví dụ:

- `startupProbe` dành ngân sách khởi động khoảng `30 × 10 = 300` giây. Trong khi startup probe chưa thành công, kubelet chưa chạy liveness/readiness probe. Sau khi thành công, startup probe kết thúc nhiệm vụ.
- `livenessProbe` phát hiện tình trạng cần khởi động lại sau giai đoạn khởi động.
- `readinessProbe` theo dõi khả năng nhận lưu lượng trong suốt thời gian phục vụ.
- `timeoutSeconds` giới hạn thời gian chờ của mỗi lần kiểm tra; `failureThreshold` là số lần thất bại liên tiếp cần đạt. Các khoảng thời gian phải được chọn từ số đo thực tế.

Readiness chưa sẵn sàng không bảo vệ container khỏi liveness thất bại. Startup probe giúp tránh vòng lặp khởi động lại khi ứng dụng khởi động chậm. Kubelet đánh giá kết quả HTTP, không phân tích chuỗi `"UP"` trong JSON; dải mã HTTP thành công của HTTP probe là `200` đến dưới `400`. [Kubernetes: cấu hình liveness, readiness và startup probe](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)

Probe HTTP thông thường đi tới IP của Pod và cổng container đã chỉ định. Không cần đưa đường dẫn probe qua Ingress để kubelet gọi được. Sau triển khai, dùng `kubectl describe pod` với tên Pod thực tế để xem sự kiện kiểm tra thất bại; gọi URL thành công từ máy cá nhân chỉ kiểm chứng một phần đường truyền.

## 7. Khi Actuator dùng cổng quản trị riêng

Giả sử ứng dụng phục vụ nghiệp vụ ở `8080`, Actuator ở `8081`. Khi đó hai URL gốc của probe nằm trên cổng `8081`. Một phép kiểm tra trên cổng quản trị có thể thành công trong khi cổng nghiệp vụ không nhận được kết nối.

Thay toàn bộ cấu hình ví dụ bằng:

```yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
        add-additional-paths: true
```

Cấu hình `add-additional-paths` thêm hai đường dẫn trên cổng chính:

| Đường dẫn | Cổng trong ví dụ | Nhóm health |
| --- | --- | --- |
| `/actuator/health/liveness` | `8081` | `liveness` |
| `/actuator/health/readiness` | `8081` | `readiness` |
| `/livez` | `8080` | `liveness` |
| `/readyz` | `8080` | `readiness` |

Các đường dẫn gốc vẫn tồn tại; đường dẫn bổ sung là cách truy cập cùng nhóm health. Chúng không nằm ở `/actuator/livez`. Thuộc tính thêm đường dẫn mặc định là `false` và không thay thế thuộc tính bật probe. [Thuộc tính probe của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator)

Kiểm tra:

```shell
curl -i http://localhost:8081/actuator/health/liveness
curl -i http://localhost:8081/actuator/health/readiness
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
```

Nếu chọn probe trên cổng chính, đổi đường dẫn trong đoạn cấu hình Kubernetes thành `/livez` cho startup/liveness và `/readyz` cho readiness; giữ `port: http` trỏ tới `8080`. Không đổi đường dẫn nhưng quên đổi cổng tương ứng.

Phép kiểm tra qua cổng chính giúp đi qua hạ tầng HTTP chính. Nó vẫn không chứng minh mọi API nghiệp vụ đều đúng hoặc mọi luồng xử lý đều thông suốt.

## 8. Dùng probe ngoài Kubernetes

Sau khi bật `management.endpoint.health.probes.enabled=true`, một hệ thống ngoài Kubernetes cũng có thể gọi các URL này. Cần xác định rõ thành phần nào chịu trách nhiệm hành động:

| Môi trường | Có thể dùng endpoint như thế nào? | Điều cần cấu hình thêm |
| --- | --- | --- |
| Máy cá nhân | Gọi bằng `curl` để xác minh trạng thái và URL. | Không có hành động tự động chỉ vì endpoint tồn tại. |
| VM có bộ cân bằng tải | Gọi readiness để quyết định đưa thể hiện ứng dụng vào tập đích nhận lưu lượng. | Chính sách kiểm tra, ngưỡng và hành vi của bộ cân bằng tải. |
| Container chạy bằng Docker | Bộ kiểm tra sức khỏe container gọi một URL đã bật. | Lệnh kiểm tra và chính sách xử lý của hệ thống quản lý container. |
| Hệ thống giám sát | Thu thập trạng thái, phát hiện lỗi và cảnh báo. | Cơ chế thông báo hoặc tự phục hồi riêng. |

Ví dụ lệnh kiểm tra readiness dùng cho một công cụ chạy lệnh:

```shell
curl --fail --silent --show-error --max-time 2 http://localhost:8080/actuator/health/readiness
```

Lệnh này cần có `curl` trong chính môi trường thực thi. Nếu dùng bên trong container, `localhost` là container đó; nếu chạy trên máy chủ hay container khác, địa chỉ phải phù hợp. Không giả định mọi image Java tối giản đều có `curl`.

Docker đánh dấu container không khỏe và một hệ thống tự động khởi động lại container là hai cơ chế cần kiểm tra riêng; đừng suy luận hành động chỉ từ tên trạng thái. Tương tự, thay đổi trạng thái readiness không khiến Spring MVC tự từ chối mọi yêu cầu nghiệp vụ gửi thẳng tới ứng dụng: thành phần định tuyến phải sử dụng tín hiệu này.

## 9. Đọc kết quả và tránh tín hiệu sai

Khi ứng dụng đã khởi động ổn định và dùng cấu hình mặc định:

| Trạng thái ứng dụng | Health tương ứng | Mã HTTP mặc định |
| --- | --- | --- |
| `LivenessState.CORRECT` | `UP` | `200` |
| `LivenessState.BROKEN` | `DOWN` | `503` |
| `ReadinessState.ACCEPTING_TRAFFIC` | `UP` | `200` |
| `ReadinessState.REFUSING_TRAFFIC` | `OUT_OF_SERVICE` | `503` |

Spring Boot tự chuyển các trạng thái theo vòng đời. Sau khi context khởi tạo thành công, ứng dụng có thể được xem là còn sống; readiness được chấp nhận sau các runner khởi động. Một nhóm health cũng có thể tổng hợp thêm chỉ báo nếu được cấu hình. [Spring Boot: vòng đời và trạng thái ứng dụng](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability)

Các mã HTTP ở trên giả định chưa tùy chỉnh ánh xạ health status. Không ánh xạ `DOWN` hoặc `OUT_OF_SERVICE` thành `200` chỉ để probe thành công; làm vậy khiến hạ tầng mất tín hiệu lỗi.

Không dùng health tổng hợp thay cho liveness một cách máy móc: một dịch vụ bên ngoài tạm lỗi không nhất thiết được sửa bằng việc khởi động lại mọi thể hiện ứng dụng. Theo mặc định, các nhóm probe không tự gom mọi chỉ báo cơ sở dữ liệu, cache hay dịch vụ khác. Việc thêm phụ thuộc vào readiness cần dựa trên khả năng thực sự phục vụ khi phụ thuộc đó lỗi. [Spring Boot 3.3: kiểm tra trạng thái bên ngoài](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes.external-state)

Nếu ứng dụng có Spring Security hoặc proxy, bảo đảm bên gọi probe nhận đúng phản hồi health. `401`/`403` có thể là lỗi quyền truy cập; chuyển hướng tới trang đăng nhập có thể che mất trạng thái thật. Chỉ cho phép truy cập phù hợp tới các đường dẫn probe đã chọn, giữ chính sách bảo vệ cho endpoint quản trị khác và không cần công bố chi tiết health nhạy cảm.

## 10. Chẩn đoán theo từng lớp

| Hiện tượng | Kiểm tra theo thứ tự |
| --- | --- |
| `/actuator/health` hoạt động, URL probe trả `404` | Phiên bản đang dùng; thuộc tính `management.endpoint.health.probes.enabled`; môi trường được nhận diện; cấu hình/profile đang có hiệu lực. |
| Tất cả URL health trả `404` | Có starter Actuator và máy chủ web chưa; health có bị tắt hoặc bị loại khỏi HTTP exposure không; base path/context path/cổng có đổi không. |
| `/actuator/health/readiness` trả `503` | Nhóm đã có phản hồi; xem quá trình khởi động và trạng thái readiness, không vội sửa URL. |
| Nhận `401`, `403` hoặc trang đăng nhập | Quy tắc bảo mật ứng dụng, proxy và quyền của thành phần gọi probe. |
| Connection refused hoặc hết thời gian chờ | Tiến trình đã nghe cổng chưa, địa chỉ bind, đúng IP/cổng, đường mạng và giới hạn thời gian. |
| Gọi từ máy cá nhân được nhưng Pod báo probe lỗi | URL/cổng trong Pod template, giao thức HTTP/HTTPS, khả năng kubelet tiếp cận Pod và sự kiện của Pod. |
| Actuator ở `8081` tốt nhưng cổng chính `8080` hỏng | Bật đường dẫn bổ sung và cấu hình kubelet kiểm tra cổng chính nếu phù hợp. |
| Ứng dụng cứ khởi động lại khi đang khởi tạo | Kiểm tra startup probe, thời gian khởi tạo thực tế và ngưỡng liveness; readiness thất bại không chặn liveness. |

Khi chẩn đoán, ghi lại **URL, cổng, mã HTTP, body và nơi thực hiện yêu cầu**. Những dữ kiện này giúp phân biệt lỗi tạo nhóm probe, công bố endpoint, quyền truy cập, đường mạng và trạng thái ứng dụng.

## 11. Thực hành kiểm chứng

1. Chạy ví dụ ngoài Kubernetes: hai URL probe trả `200` và body `{"status":"UP"}` sau khởi động.
2. Chạy lại với `--management.endpoint.health.probes.enabled=false`: health gốc còn, hai URL nhóm tự động không còn.
3. Bật lại probe cùng `--spring.main.cloud-platform=none`: kiểm chứng rằng ngoài Kubernetes vẫn dùng được.
4. Chuyển Actuator sang `8081`, bật đường dẫn bổ sung rồi kiểm tra cả bốn URL trong bảng.
5. Trong Pod thực tế, cấu hình startup/liveness/readiness theo đúng đường dẫn và cổng. Quan sát sự kiện Pod để xác minh kubelet đang thực hiện phép kiểm tra.

Đạt yêu cầu khi bạn giải thích được cả **vì sao URL xuất hiện** lẫn **ai đọc kết quả và hành động**, đồng thời tái lập được các trường hợp bật/tắt trên môi trường của mình.

# Phối hợp management base path với Servlet context path hoặc WebFlux base path

## 1. Nhìn URL quản trị theo từng lớp

Giả sử endpoint `health` đang được bật và công bố qua HTTP. Sau khi ứng dụng chuyển từ đường dẫn gốc sang `/app`, việc tiếp tục gọi `/actuator/health` có thể trả 404 dù Actuator vẫn hoạt động bình thường. Lý do là đường dẫn đầy đủ còn phụ thuộc tiền tố của ứng dụng và nơi máy chủ quản trị được đặt.

Để xác định URL, cần trả lời lần lượt:

1. Ứng dụng chạy theo mô hình Servlet hay WebFlux?
2. Actuator dùng chung cổng với ứng dụng hay một cổng quản trị riêng?
3. Tiền tố của ứng dụng hoặc máy chủ quản trị là gì?
4. Tiền tố nhóm endpoint và đường dẫn riêng của endpoint là gì?

Bài viết dùng Spring Boot 3.3.x, cấu hình Servlet mặc định và yêu cầu gọi trực tiếp vào máy chủ. Ví dụ thực nghiệm được kiểm tra với Boot 3.3.0, Java 21, Servlet trên Tomcat và WebFlux trên Reactor Netty.

## 2. Phân biệt các thuộc tính có chữ path

| Thuộc tính | Vai trò | Phạm vi cần nhớ |
| --- | --- | --- |
| `server.servlet.context-path` | Đường dẫn ngữ cảnh của ứng dụng Servlet, ví dụ `/app` | Là tiền tố chung của ứng dụng Servlet; khi dùng chung cổng, đường dẫn Actuator nằm dưới tiền tố này |
| `spring.webflux.base-path` | Đường dẫn gốc của ứng dụng WebFlux, ví dụ `/api` | Là tiền tố tương ứng cho ứng dụng reactive khi dùng chung cổng |
| `management.endpoints.web.base-path` | Tiền tố của nhóm endpoint Actuator, mặc định `/actuator` | Ví dụ đổi thành `/manage`; được ghép bên dưới gốc phù hợp với chế độ cổng |
| `management.server.base-path` | Đường dẫn gốc của máy chủ quản trị riêng, ví dụ `/ops` | Dùng khi cổng quản trị thực sự tách khỏi cổng ứng dụng |
| `management.endpoints.web.path-mapping.health` | Đổi phần đường dẫn của endpoint có ID `health` | Ví dụ `ready`; không đổi ID endpoint trong danh sách công bố |

Không cộng `server.servlet.context-path` và `spring.webflux.base-path` với nhau như hai lớp bắt buộc. Chọn thuộc tính tương ứng với loại ứng dụng đang thực sự chạy.

Theo tài liệu Boot 3.3, khi dùng chung cổng, management endpoint base path nằm dưới Servlet context path hoặc WebFlux base path; khi tách cổng, nó nằm dưới management server base path. [Quan hệ giữa các đường dẫn HTTP quản trị](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.customizing-management-endpoint-paths).

## 3. Trường hợp Servlet dùng chung cổng

Cấu hình:

```properties
server.port=8080
server.servlet.context-path=/app
management.endpoints.web.base-path=/manage
management.endpoints.web.exposure.include=health
```

Không đặt cổng quản trị riêng. Đường dẫn `health` được ghép như sau:

```text
/app/manage/health
= /app/manage/health
```

URL đầy đủ:

```text
http://127.0.0.1:8080/app/manage/health
```

Nếu một controller nghiệp vụ có ánh xạ `@GetMapping("/ping")`, URL của nó là:

```text
http://127.0.0.1:8080/app/ping
```

Tiền tố `/manage` chỉ đặt trước các endpoint Actuator; nó không tự chuyển controller `/ping` thành `/app/manage/ping`.

| URL thử trong ứng dụng mẫu không có bảo mật | Kết quả dự kiến |
| --- | --- |
| `http://127.0.0.1:8080/app/manage/health` | Tìm được endpoint health |
| `http://127.0.0.1:8080/manage/health` | Thiếu context path `/app` |
| `http://127.0.0.1:8080/app/actuator/health` | Vẫn dùng tiền tố Actuator cũ |

### 3.1. Khi giữ nguyên tiền tố mặc định của Actuator

Nếu bỏ dòng `management.endpoints.web.base-path=/manage`, tiền tố Actuator mặc định là `/actuator`. Với context path `/app`, URL trở thành:

```text
http://127.0.0.1:8080/app/actuator/health
```

Thay đổi context path không tự loại bỏ tiền tố `/actuator`.

## 4. Trường hợp WebFlux dùng chung cổng

Cấu hình tương ứng:

```properties
server.port=8080
spring.webflux.base-path=/api
management.endpoints.web.base-path=/manage
management.endpoints.web.exposure.include=health
```

Đường dẫn `health`:

```text
/api/manage/health
= /api/manage/health
```

URL đầy đủ:

```text
http://127.0.0.1:8080/api/manage/health
```

Controller có ánh xạ `/ping` được gọi tại:

```text
http://127.0.0.1:8080/api/ping
```

Trong trường hợp này, không dùng `server.servlet.context-path` như cách thay thế cho `spring.webflux.base-path`. Một ứng dụng WebFlux không trở thành ứng dụng Servlet chỉ vì tên một thuộc tính có chữ `server` được thêm vào cấu hình.

Nếu kết quả vẫn giống Servlet khi dự định chạy WebFlux, cần kiểm tra loại ứng dụng được Boot lựa chọn và các starter trên classpath. Dự án minh họa bên dưới chọn một starter web cho mỗi lần xây dựng, giúp phân biệt hai trường hợp.

## 5. Khi cổng quản trị thực sự tách riêng

Giả sử cổng ứng dụng là 8080, cổng quản trị là 8081:

```properties
server.port=8080
management.server.port=8081
management.server.base-path=/ops
management.endpoints.web.base-path=/manage
management.endpoints.web.exposure.include=health
```

Trên máy chủ quản trị, phép ghép đường dẫn là:

```text
/ops/manage/health
= /ops/manage/health
```

URL quản trị:

```text
http://127.0.0.1:8081/ops/manage/health
```

Đường dẫn này không lấy thêm context/base path của máy chủ ứng dụng làm tiền tố. Hai trường hợp cụ thể:

| Loại ứng dụng | Đường dẫn controller `/ping` trên cổng 8080 | Đường dẫn health trên cổng 8081 |
| --- | --- | --- |
| Servlet có `server.servlet.context-path=/app` | `/app/ping` | `/ops/manage/health` |
| WebFlux có `spring.webflux.base-path=/api` | `/api/ping` | `/ops/manage/health` |

Không ghép thành `/app/ops/manage/health` hoặc `/api/ops/manage/health` trên cổng quản trị. Cũng không tiếp tục thăm dò `/app/manage/health` hay `/api/manage/health` trên cổng nghiệp vụ như thể Actuator chưa chuyển cổng.

Việc tách cổng là cấu hình máy chủ quản trị riêng. [Cấu hình cổng quản trị trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.customizing-management-server-port).

### 5.1. Nếu không thêm management.server.base-path

Với cổng 8081 riêng nhưng không có tiền tố máy chủ quản trị bổ sung, `management.endpoints.web.base-path=/manage` tạo URL:

```text
http://127.0.0.1:8081/manage/health
```

Nó không tự kế thừa `/app` hoặc `/api` để trở thành đường dẫn trên cổng quản trị.

### 5.2. Khai báo cùng số cổng vẫn là dùng chung cổng

Ví dụ:

```properties
server.port=8080
management.server.port=8080
server.servlet.context-path=/app
management.endpoints.web.base-path=/manage
```

Cổng quản trị ở đây không khác cổng ứng dụng. Với cấu hình Servlet này, `health` vẫn nằm tại `/app/manage/health` trên cổng 8080.

Điểm quyết định là có **cổng quản trị riêng thực sự**, không phải chỉ có hay không một dòng tên `management.server.port` trong tệp. Trong các ví dụ thông thường, để trống thuộc tính này cũng có nghĩa là dùng cổng ứng dụng. [Thuộc tính máy chủ quản trị và cách dùng cổng ứng dụng](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/web/server/ManagementServerProperties.html).

## 6. Công thức và bảng đối chiếu nhanh

Gọi:

- `A` là tiền tố ứng dụng đang có hiệu lực: Servlet context path hoặc WebFlux base path.
- `M` là management server base path khi có máy chủ quản trị riêng.
- `E` là management endpoint base path, mặc định `/actuator`.
- `S` là đường dẫn của thao tác endpoint, chẳng hạn `/health`.

Khi đó, với cấu hình đường dẫn thông thường trong bài:

```text
Dùng chung cổng:  URL = địa chỉ máy chủ ứng dụng + A + E + S
Tách cổng:        URL = địa chỉ máy chủ quản trị + M + E + S
```

Đây là cách ghép các đoạn đường dẫn, không phải phép nối chuỗi giữ nguyên mọi dấu `/` một cách máy móc. Đoạn gốc `/` không được chèn thành hai dấu gạch chéo liên tiếp.

| Chế độ | A | M | E | Đường dẫn health trên cổng cần gọi |
| --- | --- | --- | --- | --- |
| Servlet, chung cổng | `/app` | Không dùng làm gốc quản trị riêng | `/manage` | `/app/manage/health` trên cổng ứng dụng |
| WebFlux, chung cổng | `/api` | Không dùng làm gốc quản trị riêng | `/manage` | `/api/manage/health` trên cổng ứng dụng |
| Servlet hoặc WebFlux, tách cổng | Tiền tố của ứng dụng nghiệp vụ | `/ops` | `/manage` | `/ops/manage/health` trên cổng quản trị |
| Tách cổng, không thêm M | Tiền tố của ứng dụng nghiệp vụ | Không có tiền tố bổ sung | `/manage` | `/manage/health` trên cổng quản trị |
| Servlet, chung cổng, E là gốc | `/app` | Không dùng làm gốc quản trị riêng | `/` | `/app/health` trên cổng ứng dụng |
| WebFlux, chung cổng, E là gốc | `/api` | Không dùng làm gốc quản trị riêng | `/` | `/api/health` trên cổng ứng dụng |

### 6.1. Đặt endpoint base path bằng / không xóa context/base path bên ngoài

Ví dụ Servlet:

```properties
server.servlet.context-path=/app
management.endpoints.web.base-path=/
```

`health` nằm tại `/app/health`, không phải `/health`. Tương tự, WebFlux có base path `/api` sẽ dùng `/api/health`.

### 6.2. Đổi đường dẫn riêng của health

```properties
server.servlet.context-path=/app
management.endpoints.web.base-path=/manage
management.endpoints.web.path-mapping.health=ready
management.endpoints.web.exposure.include=health
```

URL trở thành:

```text
http://127.0.0.1:8080/app/manage/ready
```

ID trong include vẫn là `health`; `ready` chỉ là đường dẫn được ánh xạ. Đây cũng không phải thao tác tạo ra một health group readiness: ví dụ chỉ đổi tên đường dẫn của endpoint health.

## 7. Thực nghiệm với cùng mã Java cho Servlet và WebFlux

Dự án nhỏ sau dùng Java 21, Gradle 8.5 và Boot 3.3.0. Cổng 8080/8081 cần sẵn sàng cho lần chạy tương ứng; nếu thay cổng, cập nhật URL thử theo cùng quy tắc.

Ứng dụng có một controller `/ping` để phân biệt tiền tố nghiệp vụ với tiền tố Actuator. Nó không thêm Spring Security, chỉ lắng nghe trên loopback. Lần xây dựng đầu cần tải plugin và thư viện.

### 7.1. Tạo các tệp

```text
actuator-path-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/lab/paths/
    │   ├── PathApplication.java
    │   └── PingController.java
    └── resources/application.properties
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'actuator-path-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

def webStack = providers.gradleProperty('webStack').getOrElse('servlet')
if (!(webStack in ['servlet', 'reactive'])) {
    throw new GradleException('webStack must be servlet or reactive')
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    if (webStack == 'reactive') {
        implementation 'org.springframework.boot:spring-boot-starter-webflux'
    } else {
        implementation 'org.springframework.boot:spring-boot-starter-web'
    }
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

tasks.named('bootJar') {
    archiveFileName = "actuator-path-demo-${webStack}.jar"
}
```

Thuộc tính Gradle `webStack` trong dự án này chọn một starter web: `servlet` dùng Spring MVC, `reactive` dùng WebFlux. Hai tệp JAR có tên riêng để lệnh chạy thể hiện rõ loại ứng dụng được xây dựng.

Tệp `src/main/java/lab/paths/PathApplication.java`:

```java
package lab.paths;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathApplication {
    public static void main(String[] args) {
        SpringApplication.run(PathApplication.class, args);
    }
}
```

Tệp `src/main/java/lab/paths/PingController.java`:

```java
package lab.paths;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
```

Controller chỉ khai báo `/ping`; nó không chép `/app`, `/api` hoặc `/manage` vào annotation. Các tiền tố bên ngoài do cấu hình môi trường xác định.

Tệp `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health
management.endpoints.web.base-path=/manage
```

### 7.2. Chạy Servlet, dùng chung cổng

```shell
gradle bootJar -PwebStack=servlet
java -jar build/libs/actuator-path-demo-servlet.jar --server.servlet.context-path=/app
```

Ở cửa sổ dòng lệnh khác:

```shell
curl -i http://127.0.0.1:8080/app/ping
curl -i http://127.0.0.1:8080/app/manage/health
curl -i http://127.0.0.1:8080/manage/health
```

Trên PowerShell Windows, dùng `curl.exe` nếu `curl` đang là bí danh.

Kết quả chính: `/app/ping` trả 200 với thân `pong`; `/app/manage/health` trả 200 trong ứng dụng mẫu khỏe mạnh; `/manage/health` trả 404 do thiếu context path.

### 7.3. Tách cổng quản trị cho Servlet

Dừng tiến trình Servlet trước bằng Ctrl+C rồi chạy:

```shell
java -jar build/libs/actuator-path-demo-servlet.jar --server.servlet.context-path=/app --management.server.port=8081 --management.server.address=127.0.0.1 --management.server.base-path=/ops
```

Thử:

```shell
curl -i http://127.0.0.1:8080/app/ping
curl -i http://127.0.0.1:8081/ops/manage/health
curl -i http://127.0.0.1:8080/app/manage/health
curl -i http://127.0.0.1:8081/app/ops/manage/health
```

Hai yêu cầu đầu trả 200 trong ứng dụng mẫu. Hai yêu cầu sau trả 404: một yêu cầu vẫn tìm Actuator trên cổng nghiệp vụ, yêu cầu còn lại cộng thừa context path.

`management.server.address=127.0.0.1` ở ví dụ này đặt địa chỉ cho máy chủ quản trị riêng; nó không quyết định các đoạn đường dẫn.

### 7.4. Chạy WebFlux, dùng chung cổng

Dừng tiến trình trước, xây dựng chế độ reactive rồi chạy:

```shell
gradle bootJar -PwebStack=reactive
java -jar build/libs/actuator-path-demo-reactive.jar --spring.webflux.base-path=/api
```

Thử:

```shell
curl -i http://127.0.0.1:8080/api/ping
curl -i http://127.0.0.1:8080/api/manage/health
curl -i http://127.0.0.1:8080/manage/health
```

Hai yêu cầu có `/api` trả 200 trong ứng dụng mẫu; yêu cầu cuối thiếu WebFlux base path nên trả 404.

### 7.5. Tách cổng quản trị cho WebFlux

Dừng tiến trình reactive trước rồi chạy:

```shell
java -jar build/libs/actuator-path-demo-reactive.jar --spring.webflux.base-path=/api --management.server.port=8081 --management.server.address=127.0.0.1 --management.server.base-path=/ops
```

Thử:

```shell
curl -i http://127.0.0.1:8080/api/ping
curl -i http://127.0.0.1:8081/ops/manage/health
curl -i http://127.0.0.1:8081/api/ops/manage/health
```

Hai yêu cầu đầu trả 200 trong ứng dụng mẫu. Yêu cầu cuối trả 404 vì cộng thêm `/api` của ứng dụng nghiệp vụ vào máy chủ quản trị riêng.

Khi sửa các tệp cấu hình đóng gói, cần xây dựng lại JAR và khởi động lại. Khi chỉ thay tham số dòng lệnh như trong bài, dừng và chạy lại đúng JAR là đủ cho lần thử đó.

## 8. Đường dẫn công khai sau reverse proxy có thể khác

Công thức trên xác định URL mà ứng dụng xử lý trực tiếp. Một reverse proxy có thể thêm hoặc loại một tiền tố trước khi chuyển yêu cầu vào ứng dụng.

Ví dụ proxy nhận đường dẫn `/platform/ops/manage/health`, loại `/platform`, rồi chuyển phần `/ops/manage/health` tới cổng quản trị. Khi đó, URL công khai có thêm `/platform`, nhưng cấu hình máy chủ quản trị không nhất thiết phải chứa tiền tố này.

Cần phân biệt:

```text
Đường dẫn bên ngoài mà người gọi gửi
    → quy tắc giữ/loại/đổi tiền tố của proxy
    → đường dẫn bên trong mà ứng dụng nhận
```

Nếu một tiền tố đã được cấu hình trong ứng dụng, đừng đồng thời cộng nó thêm lần nữa chỉ dựa vào URL công khai. Ngược lại, proxy giữ nguyên một tiền tố mà ứng dụng không có cũng có thể tạo 404.

Đổi base path không tự công bố thêm endpoint và không cấp quyền truy cập. Sau khi thay URL quản trị, cần cập nhật đúng địa chỉ trong công cụ thăm dò, cấu hình thu thập số liệu hoặc quy tắc truy cập có sử dụng đường dẫn.

## 9. Chẩn đoán theo bằng chứng

Khi URL quản trị không hoạt động, kiểm tra:

1. **Đúng tiến trình và loại web:** đang chạy JAR Servlet hay WebFlux; các tham số nào có hiệu lực?
2. **Đúng cổng:** quản trị có máy chủ riêng không; yêu cầu đang tới cổng ứng dụng hay cổng quản trị?
3. **Đúng tiền tố ngoài:** dùng context/base path của ứng dụng khi chung cổng, dùng management server base path khi tách cổng.
4. **Đúng tiền tố endpoint:** còn `/actuator`, đã đổi thành `/manage` hay đã đặt `/`?
5. **Đúng đoạn cuối:** endpoint có path mapping riêng không; ID trong include vẫn đúng không?
6. **Đúng điều kiện công bố và truy cập:** endpoint được bật, được chọn cho HTTP và người gọi có quyền không?
7. **Đúng đường đi qua proxy:** ứng dụng thực sự nhận đường dẫn nào sau khi proxy chuyển tiếp?

Trong dự án mẫu không có bảo mật, các đường dẫn không khớp trả 404. Ở hệ thống thật, 401/403 có thể đến từ kiểm soát truy cập; 503 ở một phản hồi health có thể liên quan tình trạng sức khỏe ứng dụng. Không sửa cấu hình đường dẫn chỉ dựa vào một mã lỗi mà chưa xem nội dung và nơi phát sinh phản hồi.

## 10. Lỗi thường gặp

| Nhầm lẫn | Cách sửa |
| --- | --- |
| Dùng chung cổng nhưng bỏ `/app` hoặc `/api` | Ghép tiền tố ứng dụng trước management endpoint base path |
| Tách cổng nhưng vẫn cộng `/app` hoặc `/api` lên URL quản trị | Dùng management server base path của máy chủ riêng |
| Đặt `/manage` rồi tiếp tục gọi `/actuator` | Kiểm tra giá trị endpoint base path đang có hiệu lực |
| Cho rằng `management.endpoints.web.base-path=/` xóa mọi tiền tố | Giữ nguyên lớp context/base path bên ngoài phù hợp |
| Ghép cả Servlet context path và WebFlux base path | Xác định loại ứng dụng đang chạy rồi chọn thuộc tính đúng |
| Khai báo hai cổng bằng nhau nhưng tính URL như hai máy chủ | Áp dụng quy tắc chung cổng |
| Đổi path mapping health thành ready rồi ghi `include=ready` | Giữ ID `health` trong include; chỉ đường dẫn được đổi |
| Viết sẵn `/app` trong controller rồi lại đặt context path `/app` | Để controller mô tả đường dẫn nội bộ, tránh lặp tiền tố cấu hình |
| Sửa cấu hình nhưng vẫn chạy tiến trình hoặc JAR cũ | Kiểm tra lệnh khởi động và xây dựng lại khi cần |

## 11. Tự kiểm tra

**Câu 1.** Servlet có context path `/orders`, endpoint base path `/manage`, dùng chung cổng 8080. Health ở đâu?

**Đáp án:** `http://127.0.0.1:8080/orders/manage/health`.

**Câu 2.** WebFlux có base path `/api`, endpoint base path vẫn mặc định `/actuator`, dùng chung cổng. Phần đường dẫn health là gì?

**Đáp án:** `/api/actuator/health`.

**Câu 3.** Ứng dụng có tiền tố `/api`, cổng quản trị riêng 8081, management server base path `/ops`, endpoint base path `/manage`. Có cộng `/api` lên URL quản trị không?

**Đáp án:** Không. URL quản trị trực tiếp là `http://127.0.0.1:8081/ops/manage/health`.

**Câu 4.** Servlet có context path `/app`, dùng chung cổng và đặt endpoint base path bằng `/`. Health có nằm ở `/health` không?

**Đáp án:** Không. Nó nằm tại `/app/health`.

**Câu 5.** Hai thuộc tính cổng cùng là 8080 có tạo máy chủ quản trị riêng không?

**Đáp án:** Không trong trường hợp cổng cố định này. Phải áp dụng cách ghép đường dẫn của chế độ chung cổng.

**Câu 6.** Ánh xạ đường dẫn của health thành `ready` có đổi ID endpoint thành `ready` không?

**Đáp án:** Không. ID vẫn là `health`; phần đường dẫn cuối đổi thành `/ready`.

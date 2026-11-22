# Chạy Actuator trên cổng ứng dụng hoặc cổng quản trị riêng

Ứng dụng web có hai nhóm yêu cầu thường gặp: yêu cầu nghiệp vụ từ người dùng và yêu cầu quản trị từ công cụ vận hành. Spring Boot Actuator cung cấp nhóm thứ hai, chẳng hạn đọc sức khỏe hoặc thông tin ứng dụng.

Ta có thể phục vụ cả hai nhóm trên **cùng cổng HTTP**, hoặc đưa các endpoint Actuator sang **cổng quản trị riêng**. Lựa chọn này ảnh hưởng địa chỉ truy cập, cấu hình mạng, kiểm tra sức khỏe và cách tổ chức hạ tầng quản trị.

Bài dùng **Spring Boot 3.3.x**; dự án thực hành cố định **3.3.13, Java 21, Gradle 8.5 và Spring MVC**. Các ví dụ nói về ứng dụng dùng máy chủ web nhúng, đóng gói thành JAR chạy được.

## 1. Hai cách bố trí cổng

### 1.1. Dùng chung cổng ứng dụng

Ví dụ ứng dụng lắng nghe cổng `8087`:

```text
Cổng 8087
├── /hello           → đường dẫn ứng dụng
└── /actuator/info   → endpoint quản trị
```

Cấu hình:

```properties
server.port=8087
```

Nếu không đặt `management.server.port`, Actuator HTTP dùng cùng cổng với ứng dụng. Việc có thư viện Actuator không tự mở thêm một cổng quản trị cố định nào.

Ngoài cổng, endpoint còn phải được bật, có đủ điều kiện tự cấu hình và được chọn công bố qua HTTP. Ví dụ `info` trong bài được công bố rõ bằng:

```properties
management.endpoint.info.enabled=true
management.endpoints.web.exposure.include=health,info
```

### 1.2. Dùng cổng quản trị riêng

```properties
server.port=8087
management.server.port=9087
```

Bố trí mong muốn:

```text
Cùng một tiến trình Java
├── Cổng 8087
│   └── /hello           → đường dẫn ứng dụng
└── Cổng 9087
    └── /actuator/info   → endpoint quản trị
```

Trong cơ chế tự cấu hình chuẩn của ví dụ, endpoint Actuator chuyển sang cổng quản trị; không tự nhân đôi thành hai bản giống nhau ở cả hai cổng.

Thuộc tính chọn cổng là `management.server.port`. Nó không phải `management.endpoints.web.port`. [Cấu hình cổng quản trị HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)

## 2. Ý nghĩa của các lựa chọn cổng

| Cấu hình | Kết quả cần hiểu |
| --- | --- |
| Không đặt `management.server.port` | Actuator HTTP dùng cổng ứng dụng |
| Đặt bằng giá trị cổng ứng dụng, ví dụ cả hai là `8087` | Vẫn dùng chung cổng và ngữ cảnh ứng dụng |
| Đặt cổng dương khác, ví dụ ứng dụng `8087`, quản trị `9087` | Tạo bố trí quản trị riêng với máy chủ web quản trị |
| Đặt `management.server.port=-1` | Ngừng phục vụ endpoint quản trị qua HTTP |

Đặt rõ cùng một số cổng không có nghĩa khởi động thêm máy chủ thứ hai cùng chiếm địa chỉ đó. Với các cổng cố định trong bài, Spring Boot phân biệt trường hợp cùng cổng và khác cổng để chọn cơ chế phù hợp. [API tự cấu hình ngữ cảnh quản trị](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/web/server/ManagementContextAutoConfiguration.html)

Giá trị `-1` không tắt máy chủ HTTP nghiệp vụ. Nó cũng không đồng nghĩa tắt mọi hình thức quản trị như JMX. Các kênh đó có cấu hình riêng. [Ngừng công bố quản trị qua HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)

Trong kiểm thử, có thể dùng cổng ngẫu nhiên với cấu hình thích hợp, nhưng phải lấy **cổng thực tế đã được cấp**. Số `0` không phải địa chỉ cổng để công cụ giám sát gọi trực tiếp. Các thí nghiệm của bài dùng cổng cố định để dễ đối chiếu.

## 3. Cổng riêng hoạt động trong cùng ứng dụng như thế nào?

Khi cổng quản trị trùng cổng ứng dụng, Spring Boot dùng cùng `ApplicationContext`, tức ngữ cảnh chứa các bean của ứng dụng.

Khi dùng cổng quản trị riêng, Spring Boot tạo một ngữ cảnh quản trị riêng có ngữ cảnh ứng dụng chính làm cha. Với ứng dụng servlet, phần tự cấu hình quản trị cung cấp cơ chế tạo ngữ cảnh web con và máy chủ web tương ứng. [Tự cấu hình quản trị cho ứng dụng servlet](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/web/servlet/ServletManagementContextAutoConfiguration.java)

Điều này giúp tách điểm tiếp nhận HTTP quản trị, nhưng cả hai vẫn ở trong cùng tiến trình:

- Dùng cùng JVM và bộ nhớ tiến trình.
- Cùng chịu ảnh hưởng của việc tiến trình dừng hoặc cạn tài nguyên.
- Không tạo một dịch vụ độc lập có vòng đời triển khai riêng.
- Không tự sao chép toàn bộ controller nghiệp vụ sang cổng quản trị.

Vì vậy, tách cổng là một cách tổ chức hạ tầng web và mạng. Không nên suy ra rằng nó tạo ra sự cô lập hoàn toàn về tài nguyên hoặc lỗi.

### 3.1. Chọn cổng khác không tự bật thêm endpoint

Ví dụ:

```properties
management.server.port=9087
management.endpoints.web.exposure.include=health
```

vẫn chỉ chọn `health` để công bố qua HTTP. Cổng riêng không tự làm `env`, `beans` hoặc `info` xuất hiện.

Có thể đọc các lớp quyết định theo thứ tự câu hỏi:

1. Endpoint có bật và đủ điều kiện không?
2. Endpoint có được công bố qua HTTP không?
3. Máy chủ HTTP quản trị nằm ở cổng nào?
4. Người gọi có thể kết nối và có quyền truy cập không?

## 4. Xác định đúng địa chỉ, cổng và đường dẫn

Một URL đầy đủ cần có giao thức, máy đích, cổng và các phần đường dẫn. Đổi cổng không thay thế việc xác định đúng base path.

### 4.1. Khi dùng chung cổng

Giả sử cấu hình:

```properties
server.port=8087
server.servlet.context-path=/app
management.endpoints.web.base-path=/actuator
```

Địa chỉ của `info`, khi được công bố, là:

```text
http://127.0.0.1:8087/app/actuator/info
```

Với Spring MVC dùng chung cổng, base path của Actuator được tính tương đối với `server.servlet.context-path`.

### 4.2. Khi dùng cổng riêng

Giả sử:

```properties
server.port=8087
server.servlet.context-path=/app

management.server.port=9087
management.server.base-path=/ops
management.endpoints.web.base-path=/manage
```

Địa chỉ Actuator tương ứng là:

```text
http://127.0.0.1:9087/ops/manage/info
```

Phần `/app` của ứng dụng chính không được cộng thêm vào URL quản trị này. Với cổng quản trị riêng, base path của endpoint được tính tương đối với `management.server.base-path`.

Bảng ghép đường dẫn:

| Bố trí | Tiền tố ngữ cảnh | Gốc endpoint | Đường dẫn `info` |
| --- | --- | --- | --- |
| Chung cổng | `server.servlet.context-path=/app` | `/actuator` | `/app/actuator/info` |
| Cổng riêng | `management.server.base-path=/ops` | `/manage` | `/ops/manage/info` |

Đây là hai thuộc tính có trách nhiệm khác nhau: `management.server.base-path` là gốc của máy chủ quản trị riêng, còn `management.endpoints.web.base-path` là gốc nhóm endpoint web. [Mô tả các thuộc tính quản trị](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)

### 4.3. Địa chỉ lắng nghe cũng quan trọng

Với cổng riêng, có thể chỉ cho máy chủ quản trị lắng nghe trên địa chỉ cục bộ:

```properties
server.port=8087
management.server.port=9087
management.server.address=127.0.0.1
```

`management.server.address` dùng cho bố trí có cổng quản trị riêng. Khi dùng chung cổng, máy chủ chung dùng địa chỉ của ứng dụng; không thể tạo hai địa chỉ lắng nghe độc lập chỉ bằng thuộc tính quản trị này.

Lắng nghe trên `127.0.0.1` nghĩa là nhận kết nối từ cùng môi trường mạng cục bộ. Nếu công cụ giám sát nằm ở máy hoặc vùng mạng khác, cần chọn địa chỉ và đường đi phù hợp thay vì chỉ đổi số cổng.

Trong container, địa chỉ loopback là của môi trường mạng bên trong container. Việc khai báo ánh xạ cổng bên ngoài không tự làm một tiến trình chỉ nghe loopback nhận được mọi kết nối chuyển tiếp.

## 5. Khi nào chọn cùng cổng, khi nào chọn cổng riêng?

| Nhu cầu | Dùng chung cổng | Dùng cổng riêng |
| --- | --- | --- |
| Cấu hình chạy cục bộ tối thiểu | Ít điểm cấu hình hơn | Cần thêm cổng để theo dõi |
| Hạ tầng chỉ chuyển tiếp một cổng HTTP | Thuận tiện nếu định tuyến và bảo mật theo đường dẫn | Cần bổ sung khả năng chuyển tiếp cổng quản trị |
| Chính sách mạng tách lưu lượng quản trị | Cần kiểm soát dựa vào đường dẫn hoặc tầng trung gian | Có thể áp dụng quy tắc theo cổng và địa chỉ riêng |
| Công cụ vận hành dùng địa chỉ quản trị riêng | Cần quy ước đường dẫn rõ | Có điểm truy cập riêng để cấu hình |
| Kiểm tra khả năng nhận HTTP của ứng dụng chính | Dùng cùng hạ tầng web | Cần xét thêm phép kiểm tra trên cổng chính |

Không có lựa chọn luôn tốt hơn trong mọi môi trường. Hãy bắt đầu từ cách công cụ vận hành sẽ kết nối và chính sách truy cập thực tế.

Cổng riêng không tự thêm xác thực hoặc phân quyền. Nếu có Spring Security hoặc proxy bảo vệ quản trị, cần kiểm tra quy tắc áp dụng trên đúng điểm truy cập. Danh sách exposure, quyền gọi và kết nối mạng là các lớp kiểm soát riêng.

## 6. Thực hành hoàn chỉnh: giữ nguyên JAR, đổi bố trí cổng

Ta tạo một đường dẫn ứng dụng `/hello` để quan sát máy chủ chính, đồng thời dùng endpoint Actuator `info` để quan sát máy chủ quản trị. Hai phép quan sát giúp phân biệt “ứng dụng còn nhận HTTP” và “Actuator đang ở cổng nào”.

Dự án không thêm Spring Security, proxy hoặc ánh xạ tùy biến khác. Cổng `8087` và `9087` cần trống; dừng các lần chạy trước khi đổi cấu hình. Các đầu ra bên dưới là **kết quả mong đợi với đúng dự án mẫu**.

### 6.1. Cấu trúc dự án

```text
actuator-port-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/
    │   ├── PortDemoApplication.java
    │   └── BusinessProbeController.java
    └── resources/application.properties
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'actuator-port-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Tệp `src/main/java/example/PortDemoApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PortDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PortDemoApplication.class, args);
    }
}
```

Tệp `src/main/java/example/BusinessProbeController.java`:

```java
package example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BusinessProbeController {

    @GetMapping("/hello")
    public String hello() {
        return "APP_HTTP_OK";
    }
}
```

Đường dẫn này là phép quan sát cho thí nghiệm cổng. Nó không thay thế các cơ chế kiểm tra sức khỏe hoặc sẵn sàng phục vụ của một hệ thống thực tế.

Tệp `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8087
spring.jmx.enabled=false

management.endpoints.enabled-by-default=false
management.endpoint.health.enabled=true
management.endpoint.info.enabled=true
management.endpoints.web.exposure.include=health,info
management.endpoints.web.base-path=/actuator
```

Không khai báo `management.server.port` trong tệp ban đầu. Như vậy, lần chạy đầu dùng chung cổng.

### 6.2. Biên dịch và chạy trường hợp A: cùng cổng

Tại thư mục dự án, dùng JDK 21 và Gradle 8.5:

```powershell
gradle bootJar
java -jar build/libs/actuator-port-demo-1.0.0.jar
```

Nếu dự án đã có Gradle Wrapper 8.5, có thể thay lệnh đầu bằng `.\gradlew.bat bootJar`. Gradle cung cấp đường dẫn phụ thuộc Spring và tạo JAR chạy được; không dùng `javac` đơn lẻ cho dự án này.

Mở cửa sổ PowerShell thứ hai:

```powershell
curl.exe -s http://127.0.0.1:8087/hello
```

Phần thân phản hồi mong đợi:

```text
APP_HTTP_OK
```

Kiểm tra mã HTTP của hai đường dẫn:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/hello
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/info
```

Đầu ra mong đợi:

```text
200
200
```

Cả hai được phục vụ trên cổng `8087`. Việc bật Actuator không tạo thêm cổng `9087` trong lần chạy này.

### 6.3. Trường hợp B: chuyển Actuator sang cổng riêng

Dừng lần chạy A bằng `Ctrl+C`, rồi chạy lại **cùng JAR**:

```powershell
java -jar build/libs/actuator-port-demo-1.0.0.jar --management.server.port=9087 --management.server.address=127.0.0.1
```

Trong lần khởi động mới, cần đợi cả ứng dụng và máy chủ quản trị hoàn tất khởi động. Kiểm tra bốn địa chỉ:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/hello
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/info
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:9087/actuator/info
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:9087/hello
```

Đầu ra mong đợi theo thứ tự:

```text
200
404
200
404
```

Giải thích:

- Controller ứng dụng vẫn được phục vụ ở cổng chính `8087`.
- Actuator `info` được phục vụ ở cổng quản trị `9087`.
- Đường dẫn Actuator không còn được ánh xạ ở cổng chính trong cấu hình mẫu.
- Controller `/hello` không tự được sao chép sang máy chủ quản trị.

Các kết quả `404` này thuộc dự án mẫu không có bộ lọc bảo mật hoặc ánh xạ thay thế. Ở ứng dụng khác, phải xét cả chuỗi xử lý yêu cầu trước khi diễn giải mã phản hồi.

### 6.4. Trường hợp C: đặt rõ cổng quản trị bằng cổng ứng dụng

Dừng lần chạy B, rồi chạy:

```powershell
java -jar build/libs/actuator-port-demo-1.0.0.jar --management.server.port=8087
```

Mỗi lệnh chạy là một tiến trình mới; tham số `management.server.address` ở lần B không tự được giữ lại.

Gọi lại:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/hello
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/info
```

Đầu ra mong đợi:

```text
200
200
```

Spring Boot chọn bố trí cùng cổng. Không có một máy chủ quản trị thứ hai cạnh tranh để cùng chiếm `127.0.0.1:8087`.

### 6.5. Trường hợp D: ngừng phục vụ Actuator qua HTTP

Dừng lần chạy C, rồi chạy:

```powershell
java -jar build/libs/actuator-port-demo-1.0.0.jar --management.server.port=-1
```

Kiểm tra:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/hello
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/info
```

Đầu ra mong đợi:

```text
200
404
```

Ứng dụng vẫn phục vụ controller chính; Actuator HTTP đã bị ngừng công bố. Cấu hình mẫu cũng tắt JMX riêng bằng `spring.jmx.enabled=false`; không được suy ra việc JMX tắt là tác dụng của giá trị cổng `-1`.

### 6.6. Trường hợp E: kiểm tra tiền tố đường dẫn khi tách cổng

Dừng lần chạy D, rồi chạy:

```powershell
java -jar build/libs/actuator-port-demo-1.0.0.jar --server.servlet.context-path=/app --management.server.port=9087 --management.server.address=127.0.0.1 --management.server.base-path=/ops --management.endpoints.web.base-path=/manage
```

Kiểm tra:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/app/hello
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:9087/ops/manage/info
```

Đầu ra mong đợi:

```text
200
200
```

Nếu gọi nhầm `9087/app/actuator/info`, bạn đã dùng tiền tố của ứng dụng chính và base path cũ. Đổi cổng đúng nhưng đường dẫn sai vẫn không tới endpoint mong muốn.

### 6.7. Bảng kiểm chứng các lần chạy

| Lần chạy | Đường dẫn ứng dụng | Đường dẫn Actuator `info` |
| --- | --- | --- |
| A: không đặt cổng quản trị | `8087/hello` → `200` | `8087/actuator/info` → `200` |
| B: cổng quản trị `9087` | `8087/hello` → `200` | `9087/actuator/info` → `200` |
| C: cổng quản trị bằng `8087` | `8087/hello` → `200` | `8087/actuator/info` → `200` |
| D: cổng quản trị `-1` | `8087/hello` → `200` | Không phục vụ qua HTTP Actuator |
| E: cổng riêng và tiền tố riêng | `8087/app/hello` → `200` | `9087/ops/manage/info` → `200` |

Các địa chỉ rút gọn trong bảng đều dùng `http://127.0.0.1`. Bảng chỉ mô tả dự án mẫu và không cộng dồn tham số giữa các lần chạy.

## 7. Tách cổng và kiểm tra sức khỏe

Một hệ thống giám sát có thể thấy endpoint sức khỏe trên cổng quản trị hoạt động, trong khi máy chủ HTTP chính không nhận được yêu cầu mới. Lý do là khi tách ngữ cảnh, hai phía không dùng chung toàn bộ hạ tầng web.

Do đó, trước khi chọn cổng của phép kiểm tra, hãy xác định nó cần chứng minh điều gì:

- Tiến trình và thông tin sức khỏe do Actuator báo cáo.
- Khả năng tiếp nhận HTTP trên cổng phục vụ người dùng.
- Trạng thái sẵn sàng nhận lưu lượng của ứng dụng.

Với các nhóm kiểm tra sức sống và sẵn sàng phục vụ của Spring Boot, có thể cấu hình thêm đường dẫn trên cổng chính:

```properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
```

Khi các nhóm này được bật và đủ điều kiện công bố, chúng có thêm đường dẫn `/livez` và `/readyz` trên cổng ứng dụng chính. Đây là tính năng phải chủ động xét trong thiết kế; tách cổng không tự thêm các đường dẫn này trong dự án mẫu. [Health groups và probes trên cổng chính](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)

Không đồng nhất mọi phản hồi `200` của quản trị với việc mọi chức năng nghiệp vụ đều hoạt động đúng. Ngược lại, một health indicator có thể làm `health` trả trạng thái lỗi dù máy chủ web vẫn nhận được kết nối.

## 8. Các điểm cần lưu ý khi đưa vào hạ tầng

### 8.1. Cổng trong tiến trình và cổng bên ngoài là hai lớp

Đặt `management.server.port=9087` làm ứng dụng mở điểm tiếp nhận tương ứng khi cấu hình hợp lệ. Nó không tự sửa:

- Ánh xạ cổng container.
- Service hoặc định tuyến của môi trường triển khai.
- Reverse proxy, tường lửa hoặc danh sách nguồn được phép kết nối.
- Cấu hình đích của hệ thống thu thập số liệu và kiểm tra sức khỏe.

Nếu hạ tầng chỉ chuyển tiếp cổng ứng dụng, công cụ bên ngoài có thể không tới được cổng quản trị mới. Cần cập nhật đúng đường đi đã thiết kế; không suy ra từ việc ứng dụng khởi động rằng cổng đó đã truy cập được từ mọi nơi.

### 8.2. Cổng riêng và bảo mật

Tách cổng giúp áp dụng quy tắc mạng riêng. Quyền đọc hoặc thay đổi dữ liệu quản trị vẫn cần được kiểm soát thích hợp. Những endpoint có dữ liệu hoặc thao tác quản trị cần được xét theo chính sách xác thực, phân quyền và exposure.

Nếu muốn máy chủ quản trị có cấu hình TLS riêng, Spring Boot hỗ trợ nhóm `management.server.ssl.*` khi dùng cổng riêng. Việc chọn cổng và việc cấu hình giao thức, chứng thư là các quyết định liên quan nhưng khác nhau; không đổi URL từ HTTP thành HTTPS chỉ bằng cách đổi số cổng.

### 8.3. Giá trị có hiệu lực có thể khác tệp đang xem

Ví dụ tệp đặt:

```properties
management.server.port=9087
```

nhưng tiến trình chạy với:

```powershell
java -jar build/libs/actuator-port-demo-1.0.0.jar --management.server.port=8087
```

thì với cách khởi động chuẩn, tham số dòng lệnh ghi đè giá trị cùng khóa trong tệp. Biến môi trường tương ứng là `MANAGEMENT_SERVER_PORT`.

Khi chẩn đoán, kiểm tra cả profile, biến môi trường và tham số khởi động. Sửa tệp cũng không tự di chuyển cổng của tiến trình đã chạy; cần khởi động lại theo quy trình phù hợp. [Nguồn và thứ tự ưu tiên cấu hình](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)

## 9. Chẩn đoán theo bằng chứng

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| Khởi động lỗi vì cổng đã được sử dụng | Kiểm tra cổng ứng dụng và cổng quản trị; tìm tiến trình hoặc cấu hình xung đột |
| Gọi cổng mới bị từ chối kết nối | Máy chủ đã khởi động chưa; địa chỉ lắng nghe đúng chưa; có đường mạng tới đó không |
| Đã kết nối nhưng nhận `404` | Kiểm tra cổng, context path, hai base path và tập endpoint HTTP |
| Nhận `401` hoặc `403` | Kiểm tra cơ chế bảo mật thay vì chỉ thay cổng |
| Cục bộ gọi được, máy khác không gọi được | Kiểm tra loopback, địa chỉ lắng nghe, ánh xạ cổng và chính sách mạng |
| Actuator khỏe nhưng người dùng không vào được ứng dụng | Kiểm tra cổng và hạ tầng web chính; xem lại mục tiêu phép kiểm tra sức khỏe |
| Kết quả giống lần chạy cũ | Xác minh đúng PID, đúng JAR, đúng tham số và không còn tiến trình cũ |

Phản hồi HTTP như `404` nghĩa là đã nhận được phản hồi từ một máy chủ; lỗi không thể thiết lập kết nối nằm ở lớp khác. Đừng dùng hai loại bằng chứng này thay thế nhau.

Khi máy chủ quản trị không khởi động được, không xem ứng dụng là đã sẵn sàng chỉ vì trước đó có một dòng nhật ký báo cổng chính bắt đầu chạy. Hãy kiểm tra kết quả khởi động toàn ứng dụng và trạng thái thực tế của cả hai điểm truy cập.

## 10. Tự kiểm tra

1. Vì sao không cần đặt `management.server.port` để Actuator dùng cổng ứng dụng?
2. Đặt rõ cổng quản trị bằng cổng ứng dụng có tạo máy chủ thứ hai không?
3. Khi chuyển từ `8087` sang cổng quản trị `9087`, cần sửa gì ở công cụ giám sát ngoài số cổng nếu ứng dụng còn có các base path?
4. Vì sao `management.server.address=127.0.0.1` có thể khiến máy giám sát ở xa không kết nối được?
5. Tại sao `management.server.port=-1` vẫn cho phép `/hello` chạy trong ví dụ?
6. Một health check thành công trên cổng quản trị riêng còn thiếu bằng chứng gì về cổng ứng dụng chính?
7. Tách cổng có làm JVM, bộ nhớ và vòng đời triển khai tách thành hai dịch vụ độc lập không?

Bạn đã nắm được bài khi xác định được chính xác **cổng nào phục vụ yêu cầu nào**, **URL đầy đủ được ghép ra sao**, và **những gì việc tách cổng giúp kiểm soát cùng những lớp cấu hình vẫn cần xem xét**.

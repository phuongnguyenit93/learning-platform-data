# Cấu hình discovery page và giới hạn phạm vi khám phá endpoint

Khi vận hành một ứng dụng, người gọi cần biết các endpoint quản trị đang được công bố ở đâu. **Trang khám phá (discovery page)** của Actuator cung cấp các liên kết đó tại một địa chỉ gốc. Với cấu hình đường dẫn mặc định, yêu cầu `GET /actuator` trả về JSON chứa trường `_links`.

Mục tiêu của bài là cấu hình địa chỉ và sự hiện diện của trang này, chọn những endpoint có thể xuất hiện trong tập liên kết, và hiểu giới hạn của việc “ẩn trang khám phá”.

Bài áp dụng cho **Spring Boot 3.3.x**. Ví dụ chạy dùng **Spring Boot 3.3.13, Spring MVC, Java 21 và Gradle 8.5**. Những điểm liên quan đến cổng riêng và đường dẫn gốc được đối chiếu với mã nguồn đúng phiên bản này.

## 1. Discovery page giúp người gọi khám phá điều gì?

Một chương trình có thể gọi địa chỉ gốc của Actuator, đọc `_links` rồi đi theo liên kết phù hợp. Cách dùng liên kết để chỉ dẫn các thao tác tiếp theo được gọi là **hypermedia**.

Ví dụ dưới đây minh họa cấu trúc, chỉ giữ hai liên kết `self` và `info`, không biểu diễn toàn bộ phản hồi:

```json
{
  "_links": {
    "self": {
      "href": "http://127.0.0.1:8087/actuator",
      "templated": false
    },
    "info": {
      "href": "http://127.0.0.1:8087/actuator/info",
      "templated": false
    }
  }
}
```

Các thành phần cần hiểu:

| Thành phần | Ý nghĩa |
| --- | --- |
| `_links` | Tập liên kết do trang khám phá trả về |
| `self` | Liên kết tới chính trang khám phá |
| Tên quan hệ, ví dụ `info` | Khóa để nhận diện liên kết tới thao tác liên quan |
| `href` | Địa chỉ hoặc mẫu địa chỉ của liên kết |
| `templated` | Cho biết địa chỉ có phải một mẫu cần điền tham số hay không |

Tập liên kết có thể có cả những thao tác dùng đường dẫn tham số. Vì vậy, số khóa trong `_links` không phải lúc nào cũng bằng số endpoint cộng một.

Trong triển khai mặc định, `EndpointLinksResolver` xây dựng liên kết từ tập endpoint web đã được cung cấp và URL của yêu cầu. Trang này không quét mạng, không liệt kê tất cả controller nghiệp vụ và không tạo danh mục MBean JMX. [Cơ chế tạo liên kết ở Spring Boot 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/web/EndpointLinksResolver.java)

“Page” ở đây có thể hiểu là tài nguyên JSON để khám phá; không cần có một giao diện HTML hoặc Swagger UI.

## 2. Bật hoặc tắt trang khám phá

Thuộc tính điều khiển là:

```properties
management.endpoints.web.discovery.enabled=true
```

Giá trị mặc định là `true`. Có thể viết dạng YAML:

```yaml
management:
  endpoints:
    web:
      discovery:
        enabled: true
```

Để ngừng đăng ký trang khám phá:

```properties
management.endpoints.web.discovery.enabled=false
```

Thuộc tính nằm dưới `management.endpoints.web` vì nó cấu hình hành vi của nhóm endpoint web. Không dùng `management.endpoint.discovery.enabled`, và không thêm một mã `discovery` vào `exposure.include` để bật trang.

Giá trị `true` vẫn phải kết hợp với điều kiện đăng ký ánh xạ đường dẫn phù hợp. Phần 5 giải thích trường hợp đường dẫn gốc `/`. [Thuộc tính discovery trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)

### 2.1. Tắt discovery không tắt các endpoint bên dưới

Trong Spring MVC, Actuator đăng ký các thao tác endpoint và ánh xạ trang liên kết qua hai nhánh riêng. Cờ discovery quyết định việc đăng ký ánh xạ liên kết.

Do đó, nếu vẫn công bố `info`, cấu hình `discovery.enabled=false` có thể khiến:

- `GET /actuator` không còn được handler discovery xử lý.
- `GET /actuator/info` vẫn được endpoint `info` xử lý.

Mã HTTP cụ thể còn tùy các controller, tài nguyên và bộ lọc trong ứng dụng. Với dự án tối thiểu của bài, hai yêu cầu trên lần lượt cho kết quả mong đợi `404` và `200`. [Cách đăng ký handler endpoint và handler liên kết](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/web/servlet/AbstractWebMvcEndpointHandlerMapping.java)

## 3. Chọn phạm vi endpoint có thể được khám phá

Cần phân biệt ba lớp cấu hình:

| Lớp quyết định | Cơ chế | Tác động |
| --- | --- | --- |
| Khả năng hoạt động của endpoint | `management.endpoint.<id>.enabled` | Cho phép hoặc vô hiệu hóa endpoint |
| Tập công bố HTTP | `management.endpoints.web.exposure.include/exclude` | Chọn endpoint được đưa ra qua HTTP |
| Trang cung cấp liên kết | `management.endpoints.web.discovery.enabled` | Bật hoặc tắt trang liên kết tại đường dẫn gốc |

Trong cấu hình tự động thông thường, tập endpoint web đã được chọn là đầu vào cho việc tạo liên kết. Nếu muốn thu hẹp tập đó, dùng danh sách công bố:

```yaml
management:
  endpoints:
    web:
      discovery:
        enabled: true
      exposure:
        include:
          - health
          - info
```

Khi `health` và `info` đã bật, đủ điều kiện và không có bộ lọc tùy biến, trang khám phá có thể cung cấp các liên kết tương ứng.

Nếu bổ sung:

```properties
management.endpoints.web.exposure.exclude=info
```

thì `info` bị loại khỏi tập công bố HTTP, kể cả khi mã đó vẫn nằm trong `include`. Liên kết của nó cũng không còn trong trang khám phá mặc định.

Các danh sách chứa **mã endpoint**, chẳng hạn `health`, không phải đường dẫn `/actuator/health`. `exclude` được ưu tiên khi trùng với `include`. [Quy tắc bật và công bố endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

### 3.1. Giới hạn tập công bố khác với chỉ bỏ trang liên kết

Hai ý định dẫn đến hai lựa chọn khác nhau:

- Muốn các công cụ vẫn gọi trực tiếp endpoint, nhưng không dùng trang liên kết: đặt `discovery.enabled=false`.
- Muốn một endpoint không còn được phục vụ qua HTTP Actuator: loại nó bằng cấu hình exposure phù hợp.

Nếu cần vô hiệu hóa endpoint ở cấp chung, dùng thuộc tính `enabled` của endpoint, có xét các điều kiện tự cấu hình. Discovery chỉ liên quan đến trang khám phá của kênh web.

Không có một danh sách cấu hình chuẩn kiểu `discovery.include` để tạo “danh mục nhỏ” độc lập với tập công bố trong bài này. Nếu yêu cầu sản phẩm cần một danh mục riêng nhưng vẫn giữ toàn bộ endpoint phía sau, đó là một thiết kế bổ sung, cần được phân biệt với cấu hình Actuator có sẵn.

### 3.2. Không dùng số lượng liên kết để khẳng định độ an toàn

Một trang có ít liên kết không chứng minh các đường dẫn khác đã bị chặn. Một trang không còn được phục vụ cũng không chứng minh endpoint trực tiếp đã biến mất.

Muốn kiểm tra kết quả, cần quan sát cả hai:

1. Trang khám phá trả gì và có những quan hệ liên kết nào.
2. Yêu cầu trực tiếp tới endpoint mục tiêu còn được xử lý hay không.

## 4. Đặt địa chỉ cho trang khám phá

### 4.1. Đổi base path của Actuator

```properties
management.endpoints.web.base-path=/manage
```

Với ứng dụng dùng cùng cổng, không đặt context path khác:

| Tài nguyên | Địa chỉ mặc định | Sau khi đổi base path |
| --- | --- | --- |
| Trang khám phá | `/actuator` | `/manage` |
| Endpoint `info` | `/actuator/info` | `/manage/info` |

Trang khám phá đi cùng gốc Actuator; không mặc định nằm ở `/manage/discovery`.

Nếu ứng dụng servlet có `server.servlet.context-path=/app` và vẫn dùng chung cổng, các địa chỉ trên còn có tiền tố `/app`. Chẳng hạn discovery trở thành `/app/manage`.

### 4.2. Dùng cổng quản trị riêng

Có thể cấu hình:

```properties
server.port=8087
management.server.port=9087
management.server.address=127.0.0.1
management.endpoints.web.base-path=/manage
```

Trong trường hợp không có tiền tố quản trị bổ sung, trang khám phá nằm tại:

```text
http://127.0.0.1:9087/manage
```

Với cổng quản trị riêng, base path của endpoint được tính tương đối với `management.server.base-path`. Khi dùng chung cổng, nó được tính tương đối với context path của ứng dụng servlet. Cần xác định cả cổng lẫn các tiền tố khi tìm trang khám phá. [Đường dẫn và cổng quản trị HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)

Chuyển sang một cổng khác giúp tách điểm truy cập quản trị; việc ai có thể kết nối đến cổng đó vẫn phụ thuộc địa chỉ lắng nghe, mạng và quy tắc bảo mật.

## 5. Trường hợp đặc biệt: base path là `/`

Tài liệu tham chiếu 3.3 mô tả việc tắt discovery khi đường dẫn quản trị là `/` để tránh xung đột với các ánh xạ khác. Khi đọc quy tắc này, cần xét thêm **cổng dùng chung hay cổng riêng**.

Trong triển khai Spring MVC 3.3.13:

- Base path `/` được chuẩn hóa thành chuỗi rỗng.
- Handler discovery được đăng ký khi cờ discovery bật **và** ít nhất một trong hai điều kiện đúng: base path sau chuẩn hóa không rỗng, hoặc dùng cổng quản trị riêng.

Có thể ghi lại điều kiện dưới dạng mô hình logic:

```text
đăng ký discovery =
    discovery được bật
    VÀ (base path không rỗng HOẶC cổng quản trị khác cổng ứng dụng)
```

Bảng kết quả, giả sử các điều kiện tự cấu hình web còn lại đã đáp ứng:

| discovery.enabled | Base path | Cổng | Handler discovery |
| --- | --- | --- | --- |
| `true` | `/actuator` | Chung | Được đăng ký |
| `false` | `/actuator` | Chung | Không đăng ký |
| `true` | `/` | Chung | Không đăng ký |
| `true` | `/` | Riêng | Có thể đăng ký tại gốc cổng quản trị |
| `false` | `/` | Riêng | Không đăng ký |

Đây là điểm mô tả khái quát trong tài liệu chưa bao quát hết điều kiện thực thi của Spring MVC 3.3.13. Không nên suy ra rằng đặt `/` luôn tắt discovery ở mọi cấu hình cổng. Nếu ý định là tắt trang, hãy đặt rõ `management.endpoints.web.discovery.enabled=false`.

Có thể đối chiếu phần chuẩn hóa trong [`WebEndpointProperties`](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/endpoint/web/WebEndpointProperties.java) và điều kiện đăng ký trong [`WebMvcEndpointManagementContextConfiguration`](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/endpoint/web/servlet/WebMvcEndpointManagementContextConfiguration.java).

## 6. Thực hành: kiểm tra trang liên kết và endpoint trực tiếp

Dự án mẫu không thêm Spring Security, controller nghiệp vụ hoặc ánh xạ tài nguyên tùy biến. Ứng dụng chỉ lắng nghe máy cục bộ ở cổng `8087`; cần bảo đảm cổng trống trước khi chạy.

Các kết quả dưới đây là **kết quả mong đợi trong đúng dự án mẫu**, không phải suy luận chỉ từ một mã HTTP ở ứng dụng bất kỳ.

### 6.1. Tạo dự án tối thiểu

```text
actuator-discovery-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/DiscoveryPageApplication.java
    └── resources/application.properties
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'actuator-discovery-demo'
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

Tệp `src/main/java/example/DiscoveryPageApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DiscoveryPageApplication {

    public static void main(String[] args) {
        SpringApplication.run(DiscoveryPageApplication.class, args);
    }
}
```

Tệp `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8087
spring.jmx.enabled=false

management.endpoints.enabled-by-default=false
management.endpoint.health.enabled=true
management.endpoint.info.enabled=true

management.endpoints.web.base-path=/actuator
management.endpoints.web.discovery.enabled=true
management.endpoints.web.exposure.include=health,info
```

Dự án chỉ bật rõ hai endpoint đang cần quan sát. Không cần tự tạo một controller tên `discovery`.

### 6.2. Trường hợp A: trang khám phá bật

Tại thư mục dự án, dùng JDK 21 và Gradle 8.5:

```powershell
gradle bootJar
java -jar build/libs/actuator-discovery-demo-1.0.0.jar
```

Nếu đã có Gradle Wrapper 8.5, có thể thay lệnh đầu bằng `.\gradlew.bat bootJar`. Gradle cung cấp các thư viện Spring và tạo JAR chạy được; không biên dịch chương trình này bằng `javac` đơn lẻ.

Trong một cửa sổ PowerShell khác:

```powershell
$page = Invoke-RestMethod -Uri 'http://127.0.0.1:8087/actuator'
$page._links.PSObject.Properties.Name -contains 'info'
$page._links.info.href
```

Đầu ra mong đợi:

```text
True
http://127.0.0.1:8087/actuator/info
```

Phép kiểm tra dựa vào sự có mặt của liên kết `info`, không dựa vào thứ tự các khóa hoặc tổng số liên kết.

Kiểm tra endpoint trực tiếp:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/info
```

Đầu ra mong đợi:

```text
200
```

`curl.exe` gọi cURL trên Windows; `-o NUL` bỏ phần thân để phép kiểm tra chỉ in mã HTTP.

### 6.3. Trường hợp B: tắt trang, giữ nguyên endpoint

Dừng lần chạy A bằng `Ctrl+C`, rồi chạy lại:

```powershell
java -jar build/libs/actuator-discovery-demo-1.0.0.jar --management.endpoints.web.discovery.enabled=false
```

Kiểm tra hai địa chỉ:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/info
```

Đầu ra mong đợi theo thứ tự hai lệnh:

```text
404
200
```

Kết quả cho thấy handler discovery đã ngừng được đăng ký, còn endpoint `info` vẫn được công bố. Một chương trình biết sẵn URL vẫn có thể gọi trực tiếp trong điều kiện mẫu.

### 6.4. Trường hợp C: giữ trang, loại `info` khỏi tập HTTP

Dừng lần chạy B, rồi chạy:

```powershell
java -jar build/libs/actuator-discovery-demo-1.0.0.jar --management.endpoints.web.exposure.exclude=info
```

Đây là lần khởi động mới; tham số tắt discovery ở lần B không tự đi theo. Cờ discovery trong tệp lại có hiệu lực là `true`.

Kiểm tra:

```powershell
$page = Invoke-RestMethod -Uri 'http://127.0.0.1:8087/actuator'
$page._links.PSObject.Properties.Name -contains 'info'
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/info
```

Đầu ra mong đợi:

```text
False
404
```

Trang khám phá vẫn được đọc thành công, nhưng không còn liên kết `info`. Endpoint trực tiếp cũng không còn được công bố qua HTTP. Hai bằng chứng này phản ánh thay đổi exposure, khác với chỉ tắt trang liên kết.

### 6.5. Trường hợp D: đổi gốc thành `/manage`

Dừng lần chạy C, rồi chạy:

```powershell
java -jar build/libs/actuator-discovery-demo-1.0.0.jar --management.endpoints.web.base-path=/manage
```

Kiểm tra:

```powershell
$page = Invoke-RestMethod -Uri 'http://127.0.0.1:8087/manage'
$page._links.info.href
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/manage/info
```

Đầu ra mong đợi:

```text
http://127.0.0.1:8087/manage/info
200
```

Địa chỉ gốc mới cung cấp các liên kết theo đường dẫn mới. Trong dự án mẫu, `/actuator` cũ không còn được dùng làm trang discovery.

### 6.6. Trường hợp E: base path `/`, vẫn chung cổng

Dừng lần chạy D, rồi chạy:

```powershell
java -jar build/libs/actuator-discovery-demo-1.0.0.jar --management.endpoints.web.base-path=/
```

Kiểm tra:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/info
```

Đầu ra mong đợi:

```text
404
200
```

Discovery không được đăng ký tại gốc dùng chung. Endpoint `info` vẫn ở `/info` vì base path của Actuator đã đổi.

Nếu thêm một controller hoặc trang chủ tại `/`, phản hồi đầu có thể khác; điều cần kiểm tra là nó có phải trang `_links` của Actuator hay không.

### 6.7. Trường hợp F: base path `/`, cổng quản trị riêng

Dừng lần chạy E, bảo đảm cổng `9087` cũng trống, rồi chạy:

```powershell
java -jar build/libs/actuator-discovery-demo-1.0.0.jar --management.endpoints.web.base-path=/ --management.server.port=9087 --management.server.address=127.0.0.1
```

Ở cấu hình Spring MVC 3.3.13 này, cổng quản trị riêng đáp ứng điều kiện đăng ký discovery:

```powershell
$page = Invoke-RestMethod -Uri 'http://127.0.0.1:9087/'
$page._links.PSObject.Properties.Name -contains 'info'
$page._links.info.href
```

Đầu ra mong đợi:

```text
True
http://127.0.0.1:9087/info
```

Đối chiếu lần E và F để thấy vì sao cần đọc điều kiện cổng khi nói về base path `/`.

### 6.8. Bảng so sánh các lần chạy

Mỗi dòng dùng tệp cấu hình ban đầu cộng đúng các tham số của lần đó:

| Trường hợp | Trang khám phá | Liên kết `info` trong trang | Endpoint `info` |
| --- | --- | --- | --- |
| A: cấu hình mẫu | `8087/actuator` có trang | Có | `8087/actuator/info` trả `200` |
| B: discovery tắt | `8087/actuator` trả `404` | Không có trang để đọc | Vẫn trả `200` |
| C: HTTP exclude `info` | Trang vẫn có | Không | `8087/actuator/info` trả `404` |
| D: base path `/manage` | `8087/manage` có trang | Có | `8087/manage/info` trả `200` |
| E: base path `/`, chung cổng | Không đăng ký ở gốc | Không có trang để đọc | `8087/info` trả `200` |
| F: base path `/`, cổng riêng | `9087/` có trang | Có | `9087/info` trả `200` |

Các địa chỉ rút gọn trong bảng đều dùng máy `127.0.0.1` và HTTP. Bảng phản ánh dự án mẫu, chưa thêm bộ lọc bảo mật hoặc proxy.

## 7. Bảo vệ phạm vi khám phá và phạm vi truy cập

Discovery là một điểm truy cập riêng cần được xét trong chính sách bảo mật. Spring Boot cung cấp matcher `EndpointRequest.toLinks()` cho trang liên kết. Matcher `EndpointRequest.toAnyEndpoint()` còn bao gồm cả trang liên kết; `excludingLinks()` cho phép tách nó khỏi tập matcher khi cần quy tắc riêng. [API `EndpointRequest` của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html)

Một chính sách có thể cho phép công cụ kiểm tra sức khỏe gọi `health`, đồng thời chỉ cho vai trò vận hành đọc trang khám phá và các endpoint quản trị khác. Khi triển khai, cần bảo vệ cả trang liên kết lẫn endpoint đích theo ý định đó.

### 7.1. Không xem `_links` là danh sách quyền của từng người

Handler mặc định gọi bộ tạo liên kết với URL yêu cầu và trả kết quả trong `_links`. Bộ tạo liên kết chuẩn không tự lọc tập liên kết theo từng vai trò của người đang đọc trang.

Từ cơ chế này có thể suy ra: một người được phép đọc discovery có thể nhìn thấy liên kết tới một endpoint mà một quy tắc bảo mật khác vẫn chặn họ gọi trực tiếp. Sự có mặt của liên kết không cấp quyền truy cập. [Handler trả trang liên kết](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/web/servlet/WebMvcEndpointHandlerMapping.java)

Tương tự, biết đường dẫn từ tài liệu, nhật ký hoặc cấu hình vẫn cho phép người gọi thử yêu cầu trực tiếp khi discovery bị tắt. Quyền gọi phải được quyết định ở lớp bảo mật thích hợp.

### 7.2. Tách đúng các mục tiêu vận hành

| Mục tiêu | Cơ chế cần dùng |
| --- | --- |
| Không cung cấp trang liên kết | `discovery.enabled=false` |
| Chỉ công bố một tập endpoint qua HTTP | `web.exposure.include/exclude` |
| Giới hạn người được đọc trang hoặc gọi endpoint | Xác thực và phân quyền HTTP |
| Giới hạn nơi có thể kết nối đến cổng quản trị | Địa chỉ lắng nghe và chính sách mạng |
| Giảm thông tin chi tiết trong phản hồi endpoint | Cấu hình riêng của endpoint tương ứng |

CORS điều khiển một phần việc trình duyệt cho phép đọc phản hồi xuyên nguồn; nó không thay thế xác thực hoặc làm một endpoint biến mất khỏi HTTP. Không cần cấu hình CORS để thực hiện các phép kiểm tra cURL và PowerShell trong bài.

## 8. Chẩn đoán và tự kiểm tra

Khi kết quả khác dự kiến, kiểm tra theo các câu hỏi cụ thể:

1. Có đang gọi đúng cổng và đầy đủ các tiền tố đường dẫn không?
2. Giá trị discovery có hiệu lực là gì; có tham số hoặc profile ghi đè không?
3. Base path có rỗng sau chuẩn hóa không, và cổng quản trị có riêng không?
4. Endpoint mục tiêu đã bật, đủ điều kiện và có nằm trong tập HTTP hiệu lực không?
5. Yêu cầu có bị bộ lọc bảo mật hoặc proxy xử lý trước khi tới handler không?
6. Liên kết đang đọc có phải phản hồi mới của đúng tiến trình sau lần khởi động lại không?

Đổi tệp cấu hình không tự bảo đảm các ánh xạ đang chạy đã được tạo lại. Với dự án mẫu, luôn dừng rồi khởi động lại bằng tham số mới. Các lỗi `401`, `403` hoặc `404` phải được đọc trong ngữ cảnh cấu hình và chuỗi xử lý; không dùng một mã đơn lẻ để suy ra toàn bộ trạng thái discovery.

Bài tập:

- Muốn `info` còn gọi trực tiếp được nhưng không cung cấp trang liên kết: thay thuộc tính nào?
- Muốn `info` không còn trong discovery và cũng không được công bố qua HTTP: thay lớp cấu hình nào?
- Vì sao một khóa liên kết có mẫu tham số khiến việc đếm khóa khác với đếm endpoint?
- Đặt base path `/` rồi chuyển từ chung cổng sang cổng riêng có thể làm discovery xuất hiện lại trong Spring MVC 3.3.13 vì sao?
- Nếu chỉ cho vai trò vận hành đọc discovery, có cần kiểm tra quyền gọi từng endpoint trực tiếp nữa không?

Câu trả lời cần chỉ ra đúng cơ chế: cờ discovery cho trang, exposure cho tập HTTP, điều kiện đường dẫn/cổng cho ánh xạ, và bảo mật cho quyền truy cập. Đó là cơ sở để giới hạn phạm vi khám phá mà vẫn kiểm soát đúng các khả năng quản trị thực tế.

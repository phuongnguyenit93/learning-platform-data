# Phân biệt lỗi 404 do sai đường dẫn, endpoint bị tắt hoặc chưa được công bố

## 1. Một mã 404, ba câu hỏi khác nhau

Bạn gọi `GET /actuator/info` và nhận `404 Not Found`. Đừng kết luận ngay rằng ứng dụng thiếu Actuator. Hãy đặt ba câu hỏi:

1. **Địa chỉ có đúng không?** Yêu cầu phải đến đúng tiến trình, cổng và đường dẫn đang được ứng dụng sử dụng.
2. **Endpoint có được bật không?** Cấu hình có thể vô hiệu hóa riêng endpoint hoặc tắt mặc định rồi chỉ bật lại một số endpoint.
3. **Endpoint có được công bố qua HTTP không?** Một endpoint được bật chưa chắc đã có đường dẫn HTTP.

Trong bài này, **endpoint ID** là tên định danh như `health`, `info` hoặc `metrics`; **đường dẫn HTTP** là địa chỉ truy cập được tạo từ cấu hình, chẳng hạn `/actuator/info`. Hai thứ liên quan nhưng không đồng nhất.

Các ví dụ dùng **Spring Boot 3.3.13, Java 21, ứng dụng Spring MVC chạy bằng JAR**. Các thuộc tính và mặc định dưới đây thuộc nhánh 3.3; khi dùng phiên bản khác, hãy đối chiếu tài liệu đúng phiên bản.

Một cách hình dung:

```text
Yêu cầu HTTP
  -> đúng nơi nhận và đúng đường dẫn?
  -> có thao tác endpoint được ánh xạ ra HTTP?
  -> được các lớp bảo mật cho phép đi tiếp?
  -> thao tác endpoint xử lý và trả kết quả
```

Đây là sơ đồ tư duy để chẩn đoán, không phải thứ tự chạy chính xác của bộ lọc Spring Security. Bộ lọc bảo mật có thể xử lý yêu cầu trước khi Spring MVC tìm ánh xạ.

**404 chỉ là dấu hiệu quan sát được. Muốn xác định nguyên nhân, cần kết hợp kết quả HTTP với cấu hình đang có hiệu lực và bằng chứng từ tiến trình đang chạy.**

## 2. Phân biệt “bật” với “công bố”

Trong Spring Boot 3.3, hầu hết endpoint tích hợp được bật mặc định; `shutdown` là ngoại lệ. Mặc định chỉ `health` được công bố qua HTTP. Các khóa cấu hình chính:

```properties
management.endpoint.info.enabled=true
management.endpoints.web.exposure.include=health,info
```

Dòng đầu điều khiển việc bật `info`; dòng sau chọn các endpoint được công bố qua HTTP. Thêm `info` vào danh sách công bố không thể khắc phục việc `info` đang bị tắt. `exposure.exclude` có ưu tiên cao hơn `exposure.include`. Đây là các cơ chế riêng được mô tả trong [tài liệu endpoint của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.enabling).

Với một ứng dụng tối giản, không có Spring Security, không có bộ lọc tùy biến và URL mặc định:

| Trường hợp của `info` | URL gọi | Kết quả dự kiến | Hướng kiểm tra |
| --- | --- | --- | --- |
| Được bật, được công bố, URL đúng | `/actuator/info` | 200 | Endpoint truy cập được |
| Được bật, được công bố, viết sai URL | `/actuators/info` | 404 | So sánh URL với cấu hình đường dẫn |
| Bị tắt, dù nằm trong danh sách công bố | `/actuator/info` | 404 | Kiểm tra `enabled` |
| Được bật, không công bố qua HTTP | `/actuator/info` | 404 | Kiểm tra danh sách công bố |
| Được bật, vừa include vừa exclude | `/actuator/info` | 404 | Kiểm tra `exclude` |

Bảng mô tả các tình huống thí nghiệm sẽ tái hiện bên dưới; không phải quy tắc suy ngược từ mã HTTP của mọi hệ thống.

Với endpoint do Spring Boot tự cấu hình, điều kiện tạo bean còn có thể xét tính sẵn sàng của endpoint. Vì vậy, **không thấy bean chưa đủ để phân biệt “bị tắt” với “không được công bố qua bất kỳ cơ chế phù hợp nào”**. Cần đọc lý do điều kiện tự cấu hình không khớp. Cơ chế này thể hiện trong [OnAvailableEndpointCondition của phiên bản 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/endpoint/condition/OnAvailableEndpointCondition.java).

## 3. Nhánh thứ nhất: gọi sai địa chỉ hoặc đường dẫn

### 3.1. Tính URL từ cấu hình, đừng đoán từ thói quen

Với cấu hình mặc định:

```text
http://localhost:8080/actuator/info
```

Hãy tách URL thành giao thức, máy chủ, cổng, đường dẫn ngữ cảnh, tiền tố Actuator và đường dẫn endpoint. Chỉ một thành phần sai cũng có thể khiến bạn gọi nhầm tài nguyên.

Ứng dụng Servlet dùng chung cổng:

```yaml
server:
  port: 8181
  servlet:
    context-path: /shop

management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info
      path-mapping:
        info: details
```

URL của `info` lúc này là:

```text
http://localhost:8181/shop/manage/details
```

`/actuator/info`, `/manage/info` hoặc `/shop/manage/info` đều không phải địa chỉ đã cấu hình. Dù đường dẫn đổi thành `details`, endpoint ID vẫn là `info`: danh sách công bố vẫn dùng `info`, và khóa bật/tắt vẫn là `management.endpoint.info.enabled`.

Khi tách cổng quản trị:

```yaml
server:
  port: 8181
  servlet:
    context-path: /shop

management:
  server:
    port: 8182
    base-path: /ops
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info
```

Trong ứng dụng Servlet chạy bằng JAR của bài, địa chỉ quản trị là:

```text
http://localhost:8182/ops/manage/info
```

Không ghép thêm `/shop` từ máy chủ ứng dụng vào đường dẫn quản trị riêng này. Nếu gọi cổng 8181, bạn đang gọi máy chủ ứng dụng.

Quy tắc chính thức: khi chung cổng, tiền tố Actuator tương đối với `server.servlet.context-path` đối với Servlet, hoặc `spring.webflux.base-path` đối với WebFlux; khi tách cổng quản trị, nó tương đối với `management.server.base-path`. Xem [cấu hình đường dẫn và cổng quản trị](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.customizing-management-server-context-path).

### 3.2. Phân biệt sai cổng với không kết nối được

Gọi một cổng không có dịch vụ lắng nghe thường dẫn đến lỗi kết nối, không phải phản hồi HTTP 404. Nếu cổng đó có một dịch vụ khác đang chạy, chính dịch vụ ấy có thể trả 404.

Vì vậy, “đã nhận được HTTP” không chứng minh rằng bạn đã đến đúng ứng dụng. Kiểm tra cổng lắng nghe, log khởi động, phiên bản triển khai và tuyến chuyển tiếp của proxy.

Nếu URL trực tiếp nội bộ hoạt động nhưng URL công khai trả 404, hãy so sánh cách proxy giữ hoặc cắt tiền tố đường dẫn. Đây là phép thử khoanh vùng: chưa cần thay đổi trạng thái endpoint khi lỗi chỉ xuất hiện sau proxy.

Không mặc định mọi dự án đều chấp nhận dấu `/` cuối đường dẫn hoặc tự chuyển hướng đường dẫn viết sai. Dùng chính xác URL được cấu hình trước.

## 4. Nhánh thứ hai: endpoint bị tắt

Ví dụ:

```yaml
management:
  endpoint:
    info:
      enabled: false
  endpoints:
    web:
      exposure:
        include: health,info
```

Bạn đã đưa `info` vào danh sách công bố, nhưng lại tắt chính endpoint đó. Cách sửa trong trường hợp thực sự cần sử dụng `info` là đổi trạng thái bật; chỉ chỉnh danh sách công bố sẽ không giải quyết nguyên nhân.

Cũng có thể cấu hình theo hướng chỉ bật những endpoint được chọn:

```yaml
management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      enabled: true
```

Ở đây `health` được bật lại; `info` chưa được bật lại. Đừng chỉ tìm một dòng `info.enabled=false`: trạng thái tắt có thể đến từ chính sách mặc định toàn cục.

Các mảnh YAML ở mục 3–5 là **những cấu hình thay thế để phân tích từng trường hợp**, không ghép tất cả thành một file có các khóa `management` trùng nhau.

### Kiểm tra cấu hình đang có hiệu lực

Một file trong mã nguồn chỉ là một nguồn cấu hình. Profile, file ngoài JAR, biến môi trường, thuộc tính JVM và tham số dòng lệnh có thể thay đổi giá trị cuối cùng.

Ví dụ, trong cách khởi chạy mặc định của Spring Boot:

```shell
java -jar target/actuator-404-lab-1.0.0.jar --management.endpoint.info.enabled=false
```

Tham số dòng lệnh có thể ghi đè giá trị trong file. Hãy kiểm tra cả lệnh khởi chạy và cấu hình triển khai thay vì chỉ đọc `application.yml`. Thứ tự ưu tiên được trình bày trong [Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

Sau khi đổi cấu hình cho thí nghiệm, dừng tiến trình cũ rồi khởi động lại. Đừng giả định sửa YAML trên đĩa sẽ tự tạo lại các endpoint của một tiến trình JAR đang chạy.

## 5. Nhánh thứ ba: endpoint chưa được công bố qua HTTP

Ví dụ:

```yaml
management:
  endpoint:
    info:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health
```

`info` được bật, nhưng danh sách HTTP chỉ chọn `health`. Việc cần kiểm tra là danh sách công bố của **web**, không phải danh sách JMX.

Nếu cấu hình như sau, `info` vẫn bị loại khỏi HTTP:

```yaml
management:
  endpoint:
    info:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
        exclude: info
```

Khi cần truy cập `info`, phải xử lý cả quy tắc loại trừ. Đừng tiếp tục thêm tên endpoint vào `include` mà bỏ qua `exclude`.

Một tên trong `management.endpoints.jmx.exposure.include` không tạo URL HTTP tương ứng. JMX và web là hai kênh công bố khác nhau.

**Không dùng `include: "*"` làm cách sửa mặc định cho mọi 404.** Với tình huống đang cần `info`, hãy công bố đúng `health,info`; mở thêm endpoint không liên quan vừa làm phép thử khó diễn giải vừa có thể lộ thêm thông tin vận hành.

## 6. Thí nghiệm chạy được: thay đổi một điều kiện để tìm nguyên nhân

### 6.1. Tạo ứng dụng tối giản

Chuẩn bị JDK 21, Maven 3.6.3 trở lên và kết nối tới Maven Central trong lần tải phụ thuộc đầu tiên; phiên bản công cụ được đối chiếu với [yêu cầu hệ thống Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/system-requirements.html). Thí nghiệm không thêm Spring Security, cơ sở dữ liệu, proxy hoặc endpoint tùy biến để giảm số yếu tố ảnh hưởng.

Cây file:

```text
actuator-404-lab/
├── pom.xml
└── src/main/java/example/Actuator404Application.java
```

Nội dung đầy đủ của `pom.xml`:

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
    <artifactId>actuator-404-lab</artifactId>
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

Nội dung đầy đủ của `src/main/java/example/Actuator404Application.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Actuator404Application {
    public static void main(String[] args) {
        SpringApplication.run(Actuator404Application.class, args);
    }
}
```

`@SpringBootApplication` kích hoạt cấu hình ứng dụng; hai starter cung cấp máy chủ HTTP và hạ tầng Actuator. Không cần tự viết controller cho `info`.

Biên dịch và đóng gói từ thư mục chứa `pom.xml`:

```shell
mvn clean package
```

Đây là ứng dụng có phụ thuộc Spring, nên dùng Maven để chuẩn bị classpath và đóng gói thay vì chạy một mình `javac Actuator404Application.java`.

Mỗi trường hợp dưới đây dùng hai cửa sổ terminal: cửa sổ thứ nhất chạy ứng dụng; cửa sổ thứ hai gửi yêu cầu. Chờ ứng dụng khởi động thành công. **Dừng tiến trình bằng Ctrl+C trước khi chạy trường hợp kế tiếp.** Các cổng 8181 và 8182 cần chưa bị chiếm.

Các lệnh dùng chương trình curl. Trên Windows PowerShell, có thể dùng `curl.exe` thay cho `curl` để tránh alias của PowerShell. Lệnh `-o /dev/null` ở dưới dành cho Bash trên Linux/macOS; nếu dùng Windows, thay `/dev/null` bằng `NUL`. Tùy chọn `-w "%{http_code}\n"` chỉ in mã HTTP và một ký tự xuống dòng.

### 6.2. Mốc đối chứng: đường dẫn đúng và endpoint sẵn sàng

Khởi chạy:

```shell
java -jar target/actuator-404-lab-1.0.0.jar --server.port=8181 --management.endpoint.info.enabled=true --management.endpoints.web.exposure.include=health,info
```

Gửi lần lượt:

```shell
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8181/actuator/health
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8181/actuator/info
```

Stdout của hai lệnh curl:

```text
200
200
```

Trong ứng dụng tối giản này, `info` không có thông tin đóng góp thêm, nên phần thân JSON có thể là `{}`; điều đó không có nghĩa endpoint bị lỗi.

Giữ nguyên tiến trình và thử viết sai tiền tố:

```shell
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8181/actuators/info
```

Stdout:

```text
404
```

**Bằng chứng phân biệt:** chỉ thay URL mà chuyển được từ 404 sang 200 trong cùng tiến trình. Không cần thay `enabled` hay `exposure`.

### 6.3. Tắt endpoint, giữ nguyên việc công bố

Dừng tiến trình rồi chạy:

```shell
java -jar target/actuator-404-lab-1.0.0.jar --server.port=8181 --management.endpoint.info.enabled=false --management.endpoints.web.exposure.include=health,info
```

Gọi:

```shell
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8181/actuator/health
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8181/actuator/info
```

Stdout:

```text
200
404
```

So với mốc đối chứng, URL và danh sách công bố không đổi; chỉ trạng thái bật của `info` thay đổi. Đây là bằng chứng trong thí nghiệm cho nguyên nhân **endpoint bị tắt**.

### 6.4. Bật endpoint, bỏ nó khỏi danh sách HTTP

Dừng tiến trình rồi chạy:

```shell
java -jar target/actuator-404-lab-1.0.0.jar --server.port=8181 --management.endpoint.info.enabled=true --management.endpoints.web.exposure.include=health
```

Gọi lại hai URL ở mục 6.3. Stdout:

```text
200
404
```

Lần này `enabled=true`, nhưng `include` không có `info`. Kết quả HTTP trông giống mục 6.3; cấu hình và phép thử có kiểm soát mới cho biết nguyên nhân khác nhau.

Có thể kiểm tra ưu tiên loại trừ bằng lần chạy riêng:

```shell
java -jar target/actuator-404-lab-1.0.0.jar --server.port=8181 --management.endpoint.info.enabled=true --management.endpoints.web.exposure.include=health,info --management.endpoints.web.exposure.exclude=info
```

Gọi lại hai URL: vẫn nhận lần lượt 200 và 404. Bỏ quy tắc `exclude=info` rồi khởi động lại với mốc đối chứng sẽ khôi phục `info`.

### 6.5. Đổi đường dẫn, giữ nguyên endpoint ID

Dừng tiến trình rồi chạy:

```shell
java -jar target/actuator-404-lab-1.0.0.jar --server.port=8181 --server.servlet.context-path=/shop --management.endpoints.web.base-path=/manage --management.endpoints.web.path-mapping.info=details --management.endpoint.info.enabled=true --management.endpoints.web.exposure.include=health,info
```

Gọi:

```shell
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8181/actuator/info
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8181/shop/manage/details
```

Stdout:

```text
404
200
```

Trạng thái `info` vẫn đúng. Sửa danh sách công bố sẽ không sửa được URL cũ.

### 6.6. Kiểm chứng cổng quản trị riêng

Dừng tiến trình rồi chạy:

```shell
java -jar target/actuator-404-lab-1.0.0.jar --server.port=8181 --server.servlet.context-path=/shop --management.server.port=8182 --management.server.base-path=/ops --management.endpoints.web.base-path=/manage --management.endpoint.info.enabled=true --management.endpoints.web.exposure.include=health,info
```

Gọi:

```shell
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8181/shop/manage/info
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8182/ops/manage/info
```

Stdout:

```text
404
200
```

Cổng ứng dụng vẫn có máy chủ trả lời nên yêu cầu đầu nhận được 404. Yêu cầu thứ hai đến đúng cổng và đường dẫn quản trị.

## 7. Những dấu hiệu dễ dẫn đến kết luận sai

### 7.1. `/actuator` trả 404 chưa chứng minh mọi endpoint đều mất

Trang gốc Actuator là trang liên kết khám phá, không phải bản thân tất cả endpoint con. Để quan sát sự khác biệt, chạy một lần riêng:

```shell
java -jar target/actuator-404-lab-1.0.0.jar --server.port=8181 --management.endpoint.info.enabled=true --management.endpoints.web.exposure.include=health,info --management.endpoints.web.discovery.enabled=false
```

Gọi:

```shell
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8181/actuator
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8181/actuator/info
```

Stdout:

```text
404
200
```

Do đó, hãy thử trực tiếp endpoint cần chẩn đoán. Trang liên kết cũng không phải danh sách bảo đảm mọi tài nguyên con đều tồn tại. Có thể đối chiếu cờ khám phá và ánh xạ đường dẫn trong [WebEndpointProperties của Spring Boot 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/endpoint/web/WebEndpointProperties.java).

### 7.2. 404 của tài nguyên con khác với mất endpoint gốc

Ví dụ, một lần gọi `/actuator/metrics` trả danh sách tên số đo thành công, nhưng một tên số đo gõ sai ở `/actuator/metrics/{name}` có thể trả 404. Khi ấy, đừng vội mở thêm endpoint: trước hết kiểm tra tên số đo có trong danh sách hay không.

Cấu trúc hai yêu cầu này được mô tả tại [API metrics](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html). Với thao tác đọc không trả dữ liệu, lớp ánh xạ endpoint cũng có thể trả 404; có thể đối chiếu [mã xử lý HTTP của Actuator](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/web/servlet/AbstractWebMvcEndpointHandlerMapping.java). Một 404 vì không có dữ liệu không đồng nghĩa thiếu ánh xạ cho cả endpoint.

### 7.3. Mã bảo mật không phải bằng chứng chắc chắn về ánh xạ

Trong ứng dụng thực tế, 401, 403 hoặc chuyển hướng đăng nhập nên dẫn bạn kiểm tra xác thực và phân quyền. Tuy nhiên, bộ lọc có thể chặn cả URL không tồn tại; nhận 401 không chứng minh endpoint đã được công bố. Một lớp bảo mật tùy biến hoặc gateway cũng có thể cố ý trả 404.

Các thí nghiệm bên trên loại Spring Security khỏi phụ thuộc để tránh lẫn yếu tố này. Khi quay lại ứng dụng thật, dùng thông tin xác thực được cấp và kiểm tra quy tắc hiện có. Không đổi sang `permitAll()` để thử chữa một ánh xạ đang thiếu.

### 7.4. Tên endpoint đúng chưa bảo đảm đủ điều kiện tạo endpoint

Nếu cả URL, trạng thái bật và công bố đều đúng, hãy kiểm tra phụ thuộc và các điều kiện tự cấu hình. Chẳng hạn, `prometheus` cần thư viện registry phù hợp; chỉ ghi tên đó trong danh sách công bố không tự cài thư viện.

Đây là nhánh mở rộng sau khi đã loại ba nguyên nhân chính, không phải lý do để sửa đồng thời mọi cấu hình.

## 8. Quy trình chẩn đoán trên ứng dụng đang chạy

1. **Ghi lại yêu cầu nguyên bản:** phương thức, URL đầy đủ, mã HTTP, phần thân và thời điểm. Dùng `curl -i` khi cần xem cả header; không chỉ chụp dòng thông báo trong trình duyệt.
2. **Xác minh nơi trả lời:** đúng ứng dụng, phiên bản triển khai và cổng; nếu có proxy, so sánh với điểm truy cập nội bộ được phép sử dụng.
3. **Tính URL thực tế:** kiểm tra cổng quản trị, context path, base path và `path-mapping`. Thử endpoint con trực tiếp, không chỉ trang gốc.
4. **Kiểm tra trạng thái bật:** cả khóa riêng `management.endpoint.<id>.enabled` và `management.endpoints.enabled-by-default`.
5. **Kiểm tra công bố HTTP:** `web.exposure.include` và `web.exposure.exclude`. Đừng lấy cấu hình JMX để suy ra đường dẫn web.
6. **Đối chiếu cấu hình có hiệu lực:** profile đang chạy, biến môi trường, file ngoài JAR và lệnh khởi động. Xác định giá trị bị ghi đè trước khi sửa.
7. **Bổ sung bằng chứng khi còn mâu thuẫn:** xem log khởi động và báo cáo điều kiện tự cấu hình bằng một lần chạy chẩn đoán với `--debug`. Phân biệt điều kiện không khớp do bị tắt, không được công bố hoặc thiếu phụ thuộc. Không cần công bố `env`, `beans` hay `conditions` ra Internet để đọc các bằng chứng này.
8. **Thay đổi đúng một nguyên nhân đã xác định:** cập nhật URL, bật endpoint cần dùng hoặc điều chỉnh đúng danh sách công bố; khởi động lại khi cần và lặp lại cùng yêu cầu.

Ví dụ dùng log để chẩn đoán cục bộ:

```shell
java -jar target/actuator-404-lab-1.0.0.jar --debug --server.port=8181 --management.endpoint.info.enabled=false --management.endpoints.web.exposure.include=health,info
```

Tìm phần điều kiện liên quan tới `InfoEndpointAutoConfiguration`; dùng lý do điều kiện không khớp cùng cấu hình khởi chạy để xác nhận giả thuyết. Không chỉ đếm số endpoint được công bố trong một dòng log rồi kết luận endpoint cụ thể nào đã mất.

## 9. Tự kiểm tra khả năng phân biệt nguyên nhân

**Tình huống A:** `/actuator/health` trả 200, `/actuator/info` trả 404. Bạn đã biết chắc `info` bị tắt chưa?

Chưa. Kết quả mới xác nhận `health` truy cập được ở địa chỉ đó. Cần kiểm tra cả bật/tắt, công bố và ánh xạ riêng của `info`.

**Tình huống B:** `info.enabled=true`, `include=health,info`, `exclude=info`. Vì sao gọi đúng URL vẫn 404 trong ứng dụng tối giản?

`exclude` loại `info` khỏi web. Bật endpoint và đưa tên vào `include` chưa vượt qua được quy tắc loại trừ.

**Tình huống C:** Sau khi đổi tiền tố thành `/manage`, bạn gọi URL cũ và nhận 404. Cần bật lại endpoint không?

Chưa có bằng chứng cần bật lại. Trước tiên gọi URL được tính từ cấu hình mới; nếu URL mới trả 200 thì nguyên nhân là địa chỉ truy cập.

**Tình huống D:** Trang `/actuator` trả 404 nhưng `/actuator/info` trả 200.

Endpoint con đang truy cập được. Kiểm tra cấu hình khám phá hoặc đường dẫn trang liên kết thay vì kết luận Actuator đã bị tắt.

**Tình huống E:** Đã cấu hình đúng trong mã nguồn nhưng tiến trình vẫn trả kết quả cũ.

Kiểm tra đúng JAR/tiến trình, profile, nguồn cấu hình ghi đè và việc khởi động lại. Chẩn đoán phải dựa trên trạng thái tiến trình đang phục vụ yêu cầu.

Bài học cần giữ lại: **địa chỉ truy cập, trạng thái bật endpoint và việc công bố HTTP là ba trục kiểm tra độc lập. Một phép thử có đối chứng và cấu hình có hiệu lực giúp phân biệt chúng; riêng mã 404 không làm được điều đó.**

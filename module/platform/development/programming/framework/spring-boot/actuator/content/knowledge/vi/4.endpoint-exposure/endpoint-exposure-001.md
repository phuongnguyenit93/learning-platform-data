# Bật hoặc tắt từng endpoint bằng `management.endpoint.<id>.enabled`

Trong nhóm **Công bố endpoint**, việc đầu tiên cần trả lời là: ứng dụng có cho phép endpoint đó hoạt động hay không? Thuộc tính `management.endpoint.<id>.enabled` điều khiển quyết định này cho từng endpoint Actuator.

Bài dùng **Spring Boot 3.3.x**; ví dụ hoàn chỉnh cố định **3.3.13, JDK 21 và Gradle 8.5**. Các kết quả thực hành bên dưới là kết quả mong đợi với đúng cấu hình mẫu, không áp dụng máy móc cho ứng dụng đã thêm bộ lọc bảo mật hoặc tùy biến Actuator.

## 1. Hiểu đúng đối tượng được bật hoặc tắt

Một endpoint Actuator là một khả năng quản trị có mã định danh, chẳng hạn `health`, `info`, `metrics` hoặc `loggers`. Mã định danh này được dùng trong tên thuộc tính:

```properties
management.endpoint.info.enabled=true
management.endpoint.metrics.enabled=false
```

Hai dòng trên cho phép endpoint `info` hoạt động và tắt endpoint `metrics`. `<id>` là chỗ thay bằng mã định danh thực tế; không viết nguyên dấu `<` và `>` vào cấu hình.

Mã định danh khác với đường dẫn HTTP. Với đường dẫn gốc mặc định, `info` tương ứng với `/actuator/info`; khi đổi đường dẫn công bố, thuộc tính bật/tắt vẫn dùng `info`. Thuộc tính này cũng không điều khiển một `@RestController` nghiệp vụ, chẳng hạn `/orders`.

Cần phân biệt ba câu hỏi:

| Câu hỏi | Cấu hình hoặc cơ chế liên quan | Ý nghĩa |
| --- | --- | --- |
| Endpoint có được bật không? | `management.endpoint.<id>.enabled` | Cho phép hoặc vô hiệu hóa endpoint đó |
| Endpoint được công bố qua HTTP không? | `management.endpoints.web.exposure.include/exclude` | Chọn các endpoint được đưa ra qua HTTP |
| Người gửi yêu cầu có quyền gọi không? | Cấu hình bảo mật, ví dụ `SecurityFilterChain` | Kiểm soát xác thực và phân quyền |

Có thể nhớ luồng xử lý theo ba câu hỏi trên, nhưng đây không phải mô tả thứ tự chạy của mọi bộ lọc HTTP. Trong Spring Boot 3.3, endpoint được xem là khả dụng khi được bật và được công bố qua một công nghệ phù hợp. Các điều kiện tự cấu hình còn phải thỏa mãn. [Tài liệu Actuator 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

## 2. Viết cấu hình cho đúng endpoint

### 2.1. Cú pháp Properties và YAML

Dạng Properties:

```properties
management.endpoint.info.enabled=true
management.endpoint.loggers.enabled=false
```

Dạng YAML tương đương:

```yaml
management:
  endpoint:
    info:
      enabled: true
    loggers:
      enabled: false
```

Chọn một định dạng cho cùng một vị trí cấu hình. Hai khối trên là hai cách biểu diễn thay thế nhau.

Phân biệt số ít và số nhiều:

- `management.endpoint`: cấu hình riêng từng endpoint, ví dụ `info.enabled`.
- `management.endpoints`: cấu hình chung cho tập endpoint, ví dụ `enabled-by-default` hoặc `web.exposure.include`.

Vì vậy, `management.endpoints.info.enabled` đặt sai nhánh. Không nên trông chờ Spring Boot luôn báo lỗi cho mọi thuộc tính viết sai; một khóa không được cơ chế tương ứng sử dụng có thể không tạo ra tác dụng mong muốn.

Một số mã thường gặp được liệt kê trong phụ lục thuộc tính, chẳng hạn `health`, `info`, `loggers`, `metrics` và `shutdown`. Hãy dùng đúng mã: `loggers`, không phải `logger`. [Phụ lục cấu hình Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)

### 2.2. Khi không ghi thuộc tính riêng

Khai báo `@Endpoint` có thuộc tính `enableByDefault` để mô tả lựa chọn mặc định của endpoint. Giá trị mặc định của thuộc tính annotation này là `true`; một endpoint có thể khai báo khác đi. Đây là một lớp mặc định, không phải lệnh bắt buộc luôn bật. [API của `@Endpoint`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/annotation/Endpoint.html)

Với các endpoint tích hợp của Spring Boot 3.3, khi không đặt cấu hình ghi đè, `shutdown` mặc định tắt; các endpoint còn lại mặc định bật. Điều đó không bảo đảm tất cả đều có URL HTTP hoặc đều được tạo trong mọi ứng dụng: một số endpoint cần thư viện, bean hoặc thiết lập bổ sung. [Các endpoint tích hợp và điều kiện liên quan](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints)

## 3. Cấu hình riêng được ưu tiên hơn mặc định chung

Spring Boot 3.3 xác định trạng thái bật theo thứ tự:

1. Nếu có `management.endpoint.<id>.enabled`, dùng giá trị đó.
2. Nếu chưa có giá trị riêng nhưng có `management.endpoints.enabled-by-default`, dùng giá trị chung.
3. Nếu cả hai đều không được đặt, dùng `enableByDefault` của endpoint.

Bảng này áp dụng cho quyết định bật, chưa xét công bố, thư viện hay bảo mật:

| Giá trị chung | Giá trị riêng | Endpoint | Kết quả bật |
| --- | --- | --- | --- |
| Không đặt | Không đặt | `info` | `true` theo mặc định của endpoint |
| Không đặt | Không đặt | `shutdown` | `false` theo mặc định của endpoint |
| `false` | Không đặt | `info` | `false` |
| `false` | `true` | `info` | `true` |
| `true` | `false` | `info` | `false` |
| `true` | Không đặt | `shutdown` | `true` |

Điểm dễ bỏ sót là **đặt rõ giá trị chung `true` khác với không đặt** đối với endpoint có mặc định riêng là `false`, chẳng hạn `shutdown`.

Đây là hai khóa khác nhau với quy tắc ưu tiên riêng/chung, không phải cuộc so sánh vị trí hai dòng trong tệp. [Mã nguồn quyết định bật endpoint ở phiên bản 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/endpoint/condition/OnAvailableEndpointCondition.java)

### 3.1. Chọn cách cấu hình theo nhu cầu

Nếu chỉ muốn tắt một khả năng cụ thể, có thể đặt:

```properties
management.endpoint.loggers.enabled=false
```

Nếu muốn chỉ bật những endpoint đã lựa chọn rõ ràng, dùng:

```properties
management.endpoints.enabled-by-default=false
management.endpoint.health.enabled=true
management.endpoint.info.enabled=true
management.endpoints.web.exposure.include=health,info
```

Trong ví dụ thứ hai:

- Dòng đầu đặt mặc định chung là tắt.
- Hai dòng tiếp theo bật lại `health` và `info`.
- Dòng cuối chọn hai mã này để công bố qua HTTP.

Hãy đọc từng dòng theo trách nhiệm của nó. Thêm `metrics` vào danh sách công bố của ví dụ này chưa đủ để bật `metrics`; muốn dùng nó còn cần cấu hình bật phù hợp.

## 4. Tắt endpoint có tác động đến tự cấu hình

Các endpoint do Spring Boot tự cấu hình dùng điều kiện để quyết định có đăng ký bean hay không. Ví dụ, `InfoEndpointAutoConfiguration` dùng `@ConditionalOnAvailableEndpoint(endpoint = InfoEndpoint.class)` và chỉ tạo `InfoEndpoint` khi điều kiện phù hợp.

Vì vậy, khi `management.endpoint.info.enabled=false`, trong trường hợp tự cấu hình chuẩn, không nên hình dung rằng một URL vẫn tồn tại và chỉ trả về thông báo “đã tắt”. Bean endpoint tương ứng không được tự cấu hình. Việc tiêm bắt buộc bean này vào một thành phần khác có thể khiến ứng dụng không khởi động nếu bean không còn. [Tự cấu hình của `InfoEndpoint`](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/info/InfoEndpointAutoConfiguration.java)

Hai giới hạn cần giữ rõ:

- Bật endpoint không thay thế các điều kiện tạo bean khác. Ví dụ, cấu hình `MetricsEndpoint` còn yêu cầu có `MeterRegistry`.
- Tắt `metrics` là tắt endpoint đọc số liệu đó; không đồng nghĩa tắt toàn bộ Micrometer, mọi bộ đo hoặc mọi cơ chế xuất số liệu.

Có thể thấy sự tách biệt này trong `MetricsEndpointAutoConfiguration`: lớp tự cấu hình endpoint chạy sau các lớp tự cấu hình hệ thống đo và có điều kiện riêng đối với `MeterRegistry`. [Tự cấu hình của `MetricsEndpoint`](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/MetricsEndpointAutoConfiguration.java)

Phần giải thích bean ở đây nói về endpoint được Spring Boot tự cấu hình theo các điều kiện chuẩn. Không suy rộng thành lời khẳng định rằng thay thuộc tính sẽ tự xóa mọi bean do người viết ứng dụng đăng ký bằng bất kỳ cách nào.

## 5. Thực hành: quan sát bean và HTTP trước, sau khi tắt

Mục đích là thay đúng một thuộc tính của `info`, giữ nguyên danh sách công bố, rồi so sánh hai bằng chứng:

1. Spring có bean `InfoEndpoint` hay không.
2. Yêu cầu HTTP đến `/actuator/info` nhận kết quả gì.

Ví dụ là một dự án Gradle độc lập. Cần JDK 21, Gradle 8.5 và kết nối để tải phụ thuộc lần đầu. Chỉ khai báo Web và Actuator; không thêm Spring Security, endpoint tự viết hoặc bộ lọc HTTP. Ứng dụng nghe trên địa chỉ máy cục bộ `127.0.0.1:8087`.

### 5.1. Tạo dự án tối thiểu

Cấu trúc:

```text
endpoint-enable-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/EndpointEnableApplication.java
    └── resources/application.properties
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'endpoint-enable-demo'
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

Tệp `src/main/java/example/EndpointEnableApplication.java`:

```java
package example;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.info.InfoEndpoint;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class EndpointEnableApplication {

    public static void main(String[] args) {
        SpringApplication.run(EndpointEnableApplication.class, args);
    }

    @Bean
    ApplicationRunner reportInfoEndpoint(ObjectProvider<InfoEndpoint> provider) {
        return args -> System.out.println(
                "INFO_ENDPOINT_BEAN_PRESENT=" + (provider.getIfAvailable() != null));
    }
}
```

`ObjectProvider` cho phép ví dụ kiểm tra bean có mặt hay không mà không bắt buộc phải có bean đó để khởi động. Dòng in này là phép quan sát của bài thực hành, không phải một tính năng cần thêm vào mọi ứng dụng thực tế.

Tệp `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8087
spring.jmx.enabled=false

management.endpoints.enabled-by-default=false
management.endpoint.health.enabled=true
management.endpoint.info.enabled=true
management.endpoints.web.exposure.include=health,info
```

Tắt JMX trong ví dụ để chỉ quan sát đường công bố HTTP.

### 5.2. Trường hợp A: bật `info`

Tại thư mục dự án, biên dịch, đóng gói rồi chạy:

```powershell
gradle bootJar
java -jar build/libs/endpoint-enable-demo-1.0.0.jar
```

Nếu dự án đã có Gradle Wrapper 8.5, có thể thay lệnh đầu bằng `.\gradlew.bat bootJar`. Không dùng `javac` trực tiếp cho ví dụ này vì mã cần các thư viện Spring; Gradle cung cấp đường dẫn phụ thuộc và tạo JAR chạy được.

Trong các dòng stdout khi khởi động, dòng do chương trình mẫu in ra là:

```text
INFO_ENDPOINT_BEAN_PRESENT=true
```

Mở cửa sổ PowerShell thứ hai và kiểm tra mã HTTP. Dùng `curl.exe` để gọi công cụ cURL trên Windows:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/info
```

Kết quả mong đợi:

```text
200
```

Bean có mặt, endpoint được công bố và dự án mẫu không có lớp bảo mật chặn yêu cầu. Việc `info` trả về đối tượng JSON rỗng khi chưa có dữ liệu đóng góp cũng không có nghĩa endpoint bị tắt.

### 5.3. Trường hợp B: tắt `info` nhưng giữ nguyên exposure

Dừng lần chạy A bằng `Ctrl+C`. Chạy lại chính JAR đó với tham số:

```powershell
java -jar build/libs/endpoint-enable-demo-1.0.0.jar --management.endpoint.info.enabled=false
```

Tham số này thay giá trị hiệu lực của khóa riêng từ `true` trong tệp thành `false`. Danh sách `health,info` vẫn giữ nguyên.

Dòng quan sát khi khởi động:

```text
INFO_ENDPOINT_BEAN_PRESENT=false
```

Gọi lại:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/info
```

Kết quả mong đợi:

```text
404
```

Trong đúng dự án mẫu, đường dẫn này không có endpoint để xử lý, mặc dù mã `info` vẫn nằm trong danh sách công bố. Có thể kiểm tra ứng dụng còn phục vụ endpoint khác:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/health
```

Với ứng dụng mẫu đang khỏe, kết quả mong đợi là:

```text
200
```

Nếu dịch vụ thực tế có thành phần sức khỏe báo lỗi, `health` có thể trả về mã khác; mã HTTP của `health` không chỉ phụ thuộc việc bật endpoint.

### 5.4. Trường hợp C: bật lại bằng cấu hình riêng

Dừng lần chạy B rồi chạy:

```powershell
java -jar build/libs/endpoint-enable-demo-1.0.0.jar --management.endpoint.info.enabled=true
```

Giữ nguyên `management.endpoints.enabled-by-default=false` trong tệp.

Kết quả mong đợi:

| Quan sát | Giá trị |
| --- | --- |
| Dòng stdout của chương trình | `INFO_ENDPOINT_BEAN_PRESENT=true` |
| `GET /actuator/info` | HTTP `200` |
| Mặc định chung trong tệp | Vẫn là `false` |

Đây là bằng chứng rằng lựa chọn riêng `info.enabled=true` được xét trước mặc định chung.

### 5.5. Bảng đối chiếu thí nghiệm

| Lần chạy | Giá trị hiệu lực của `info.enabled` | Danh sách công bố HTTP | Có bean `InfoEndpoint` | HTTP `/actuator/info` |
| --- | --- | --- | --- | --- |
| A | `true` | `health,info` | Có | `200` |
| B | `false` | `health,info` | Không | `404` |
| C | `true` | `health,info` | Có | `200` |

Bảng là kết quả mong đợi trong các điều kiện đã nêu. Không có thay đổi Java giữa ba lần chạy; điều thay đổi là cấu hình đầu vào khi khởi động.

## 6. Giá trị trong tệp chưa chắc là giá trị hiệu lực

Có hai loại ưu tiên cần tách biệt:

- **Ưu tiên nguồn cấu hình cho cùng một khóa**: chẳng hạn giá trị dòng lệnh của `management.endpoint.info.enabled` ghi đè giá trị trong `application.properties`.
- **Ưu tiên khóa riêng so với mặc định chung**: sau khi lấy được giá trị từ môi trường cấu hình, cơ chế Actuator xét khóa riêng trước khóa chung.

Ví dụ, tệp có:

```properties
management.endpoint.info.enabled=false
```

nhưng tiến trình được chạy với:

```powershell
java -jar build/libs/endpoint-enable-demo-1.0.0.jar --management.endpoint.info.enabled=true
```

thì giá trị riêng có hiệu lực là `true` với cách khởi động chuẩn của ví dụ. Biến môi trường tương ứng là `MANAGEMENT_ENDPOINT_INFO_ENABLED`; tệp theo profile cũng có thể thay đổi cấu hình cần kiểm tra.

Khi chẩn đoán, xem cả profile đang hoạt động, biến môi trường và tham số khởi động. Sửa tệp rồi đọc lại chính tệp đó chưa đủ chứng minh tiến trình đang dùng giá trị mới. [Thứ tự nguồn cấu hình của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)

Thuộc tính bật endpoint được đánh giá trong quá trình tạo ngữ cảnh Spring. Với ứng dụng Spring Boot thông thường, sửa tệp sau khi tiến trình đã khởi động không tự động tạo hoặc gỡ bean endpoint; hãy khởi động lại bằng cấu hình mới. Bài không giả định có cơ chế làm mới ngữ cảnh bổ sung.

## 7. Các nhầm lẫn thường gặp

### 7.1. Đưa vào `include` rồi cho rằng endpoint đã bật

Cấu hình:

```properties
management.endpoint.info.enabled=false
management.endpoints.web.exposure.include=health,info
```

vẫn tắt `info`. Danh sách công bố không thay thế quyết định bật. Nếu nhu cầu là chỉ ngừng công bố qua HTTP, hãy điều chỉnh exposure HTTP thay vì dùng thuộc tính bật/tắt chung cho endpoint.

### 7.2. Đặt `enabled=true` rồi cho rằng ai cũng gọi được

Cấu hình bật không tự cấp quyền truy cập. Một endpoint đã bật vẫn có thể không được công bố hoặc bị bảo mật chặn. Khi ứng dụng có Spring Security, kết quả phải được diễn giải cùng với chuỗi bộ lọc thực tế. [Bảo mật Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security)

Không đổi toàn bộ quy tắc bảo mật chỉ để làm một thí nghiệm bật/tắt endpoint đi qua. Ví dụ tối thiểu ở trên chủ động chỉ dùng Web và Actuator để quan sát riêng hành vi đang học.

### 7.3. Dùng `404` làm bằng chứng duy nhất

Trong ví dụ B, cấu hình, dòng stdout và kết quả HTTP cùng chỉ về việc endpoint bị tắt. Ở ứng dụng khác, `404` còn có thể do sai cổng, sai đường dẫn gốc, endpoint không được công bố hoặc thiếu điều kiện tự cấu hình.

Tương tự, `401` hoặc `403` cho thấy yêu cầu gặp cơ chế bảo mật; không đủ để tự kết luận endpoint phía sau đã được đăng ký. Bộ lọc có thể xử lý yêu cầu trước khi có bước tra cứu ánh xạ endpoint.

### 7.4. Tắt `health` mà quên hệ thống kiểm tra sức khỏe

Nếu hệ thống triển khai gọi đường dẫn thuộc endpoint `health`, tắt endpoint này có thể làm yêu cầu kiểm tra không còn được phục vụ. Khi chọn chế độ mặc định tắt, cần bật rõ những endpoint mà hệ thống vận hành đang dùng.

### 7.5. Đổi tệp nhưng không khởi động lại hoặc còn giá trị ghi đè

Giữ nguyên tiến trình cũ, chạy nhầm JAR hoặc bỏ sót tham số dòng lệnh đều có thể khiến kết quả khác dự đoán. Trong thí nghiệm, dừng tiến trình trước rồi chạy lại; kiểm tra cổng và cấu hình có hiệu lực trước khi kết luận cơ chế bật/tắt bị lỗi.

## 8. Tự kiểm tra bằng một thay đổi có kiểm soát

Dùng dự án mẫu và thực hiện lần lượt; mỗi lần dừng tiến trình trước khi chạy tiếp:

1. Chạy nguyên cấu hình mẫu, dự đoán sự có mặt của `InfoEndpoint` rồi đối chiếu stdout.
2. Chạy với `--management.endpoint.info.enabled=false`, giữ nguyên exposure và gọi lại URL.
3. Bỏ dòng `management.endpoint.info.enabled=true` trong tệp, đóng gói lại và chạy không có tham số ghi đè. Giải thích vì sao mặc định chung `false` khiến `info` tắt.
4. Bật lại `info` bằng tham số dòng lệnh `true`; giải thích tại sao không cần đổi mặc định chung.
5. Trong dự án mẫu, đổi `management.endpoints.web.exposure.include` thành chỉ `health` trong khi giữ `info.enabled=true`. Giải thích vì sao chỉ nhìn giá trị `enabled` chưa thể khẳng định có URL `/actuator/info`; tự cấu hình còn xét tính khả dụng.

Bạn đã nắm được bài khi giải thích được cả ba điều: **giá trị bật đến từ đâu**, **vì sao cấu hình riêng thắng mặc định chung**, và **vì sao bật endpoint vẫn cần xét công bố cùng quyền truy cập**.

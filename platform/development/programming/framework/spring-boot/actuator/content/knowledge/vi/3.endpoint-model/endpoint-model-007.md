# Nhận diện điều kiện để endpoint tích hợp xuất hiện

## 1. Endpoint tích hợp phản ánh một khả năng đang có trong ứng dụng

Trong Actuator, endpoint tích hợp là endpoint dựng sẵn gắn với một thư viện hoặc thành phần của ứng dụng, chẳng hạn Flyway, Liquibase hay Prometheus. Để đọc thông tin của thành phần đó, Actuator cần tìm được những điều kiện tương ứng trong ứng dụng đang chạy.

Hãy hình dung endpoint là cửa quan sát: phải có thành phần cần quan sát, có đối tượng cung cấp dữ liệu, rồi mới xét việc mở cửa qua HTTP/JMX và quyền đi qua cửa. Vì vậy, thêm tên endpoint vào danh sách công bố chưa đủ để tạo ra khả năng tích hợp.

Bài này dùng Spring Boot 3.3.x, đối chiếu tài liệu 3.3.13; ví dụ dùng JDK 21. Mục tiêu là xác định điều kiện còn thiếu khi một endpoint dựng sẵn không xuất hiện, không đi sâu cấu hình nghiệp vụ của từng thư viện.

## 2. Phân biệt các câu hỏi trước khi sửa cấu hình

| Câu hỏi | Ý nghĩa khi chẩn đoán |
| --- | --- |
| Thư viện có trong classpath lúc chạy không? | Có các lớp mà tích hợp cần sử dụng hay chưa? |
| Bean nền tảng có trong ApplicationContext không? | Thành phần cần quan sát đã được Spring quản lý chưa? |
| Endpoint có được bật không? | Giá trị hiệu lực của `management.endpoint.<id>.enabled` là gì? |
| Endpoint có được công bố qua kênh đang kiểm tra không? | HTTP và JMX có danh sách công bố riêng. |
| Địa chỉ và quyền truy cập có đúng không? | Có gọi đúng cổng, đường dẫn và bằng danh tính được phép không? |
| Endpoint có dữ liệu không? | Có nguồn dữ liệu và đã phát sinh hoạt động để quan sát chưa? |

Đây là thứ tự suy luận phục vụ chẩn đoán, không phải trình tự gọi phương thức bên trong Spring Boot.

Trong Boot 3.3, `@ConditionalOnAvailableEndpoint` kiểm tra endpoint vừa được bật vừa được công bố qua công nghệ phù hợp. Do đó, điều kiện công bố có thể ảnh hưởng ngay đến việc tự động tạo bean endpoint; không nên mặc định mọi endpoint đều được tạo trước rồi chỉ bị giấu URL. [Javadoc điều kiện khả dụng của endpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/endpoint/condition/ConditionalOnAvailableEndpoint.html).

## 3. Đọc điều kiện ở cả lớp cấu hình và phương thức tạo bean

Các chú thích thường gặp:

- `@ConditionalOnClass`: chỉ áp dụng khi có lớp được yêu cầu trên classpath.
- `@ConditionalOnBean`: cần bean phù hợp trong phạm vi ApplicationContext mà điều kiện xét.
- `@ConditionalOnMissingBean`: tự động cấu hình nhường chỗ khi ứng dụng đã có bean tương ứng; điều kiện không khớp ở đây không đồng nghĩa tính năng bị mất.
- `@ConditionalOnProperty`: xét giá trị thuộc tính cấu hình.

Cần đọc cả điều kiện trên lớp cấu hình, lớp lồng và phương thức `@Bean`. Một lớp cấu hình được chọn chưa chứng minh tất cả bean trong đó đều được tạo. [Các nhóm điều kiện tự động cấu hình](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).

### Ví dụ đọc điều kiện Flyway

`FlywayEndpointAutoConfiguration` của Boot 3.3.13 có điều kiện lớp `Flyway` tồn tại và endpoint khả dụng. Phương thức tạo `FlywayEndpoint` còn yêu cầu bean `Flyway` và nhường chỗ nếu đã có endpoint tương ứng.

Từ các điều kiện này có thể suy ra: chỉ có dependency `flyway-core` chưa chứng minh ứng dụng có bean `Flyway`; chỉ có bean `DataSource` cũng chưa chứng minh có bean `Flyway`. Cần kiểm tra cấu hình tạo bean tích hợp thực tế. [Javadoc FlywayEndpointAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/flyway/FlywayEndpointAutoConfiguration.html).

## 4. Một số endpoint có điều kiện tích hợp dễ nhận diện

| Endpoint ID | Điều kiện tích hợp đáng kiểm tra | Không thể suy ra chỉ từ |
| --- | --- | --- |
| `flyway` | Lớp Flyway và ít nhất một bean `Flyway` | Có cơ sở dữ liệu hoặc có DataSource |
| `liquibase` | Lớp và bean `SpringLiquibase` trong cấu hình tích hợp Spring | Có tệp changelog trong tài nguyên |
| `httpexchanges` | Bean `HttpExchangeRepository` để cung cấp lịch sử trao đổi HTTP | Có web server hoặc starter Actuator |
| `prometheus` | Registry Prometheus, các điều kiện tự động cấu hình registry và endpoint scrape | Endpoint `metrics` đã trả dữ liệu |

Đối với Liquibase, kiểm tra kiểu bean cụ thể `liquibase.integration.spring.SpringLiquibase`, thay vì tìm mọi đối tượng có tên gần giống Liquibase. Endpoint không được tạo chỉ vì trên ổ đĩa có changelog. [Javadoc LiquibaseEndpointAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/liquibase/LiquibaseEndpointAutoConfiguration.html).

Với `httpexchanges`, Spring Boot cung cấp `InMemoryHttpExchangeRepository` để dùng trong môi trường phát triển, mặc định giữ 100 lượt trao đổi gần nhất. Việc có endpoint và việc ghi thêm dữ liệu là hai điều cần kiểm tra riêng: `management.httpexchanges.recording.enabled=false` tắt ghi nhận. [Ghi nhận trao đổi HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html).

### Trường hợp Prometheus

Dependency thông dụng là `io.micrometer:micrometer-registry-prometheus`. Trong tự động cấu hình Boot 3.3.13, còn có điều kiện về `Clock`, lớp `PrometheusMeterRegistry` và trạng thái cho phép xuất số đo Prometheus. Cấu hình lồng tạo endpoint tiếp tục xét tính khả dụng của endpoint scrape và bean đã tồn tại.

Vì vậy, hãy phân biệt ba việc: có thư viện registry, registry được cấu hình và endpoint scrape được công bố. [Mã nguồn PrometheusMetricsExportAutoConfiguration 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/export/prometheus/PrometheusMetricsExportAutoConfiguration.java).

`/actuator/metrics` phục vụ xem các số đo qua API Actuator; `/actuator/prometheus` phục vụ định dạng để Prometheus thu thập. Có số đo trong endpoint đầu chưa đủ chứng minh endpoint sau đã sẵn sàng. Thuộc tính `management.prometheus.metrics.export.enabled` điều khiển tự động cấu hình xuất số đo Prometheus, khác với `management.endpoint.prometheus.enabled` điều khiển endpoint. [Tài liệu số đo và Prometheus](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

## 5. Bật, công bố và bảo vệ endpoint là các cấu hình khác nhau

Ví dụ cấu hình HTTP:

```properties
management.endpoint.httpexchanges.enabled=true
management.endpoints.web.exposure.include=health,httpexchanges
```

Trong Boot 3.3, các endpoint dựng sẵn được bật mặc định trừ `shutdown`; mặc định chỉ `health` được công bố qua HTTP và nằm trong danh sách công bố JMX. `exclude` ưu tiên hơn `include`. Tắt endpoint bằng `enabled=false` khác với chỉ loại khỏi một kênh công bố.

Nếu Spring Security hiện diện và ứng dụng chưa khai báo `SecurityFilterChain`, Boot bảo vệ các Actuator khác `health`. Khi ứng dụng tự khai báo chuỗi bảo mật, cần đọc chính sách thực tế của ứng dụng. Danh sách công bố không cấp quyền truy cập. [Bật, công bố và bảo mật endpoint trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Ví dụ sau loại `httpexchanges` khỏi HTTP dù vẫn có trong `include`: 

```properties
management.endpoints.web.exposure.include=health,httpexchanges
management.endpoints.web.exposure.exclude=httpexchanges
```

Tăng `include` thành `*` không bổ sung bean hay dependency còn thiếu. Khi học, hãy chỉ công bố endpoint cần kiểm chứng.

JMX có cấu hình riêng, ví dụ:

```properties
spring.jmx.enabled=true
management.endpoints.jmx.exposure.include=health,httpexchanges
```

Cấu hình này vẫn cần bean repository và các điều kiện khác của endpoint. Nhìn thấy một MBean không chứng minh endpoint có URL HTTP. [Giám sát và quản lý qua JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

## 6. Thí nghiệm: giữ nguyên exposure, thay đổi bean nền tảng

### 6.1. Chuẩn bị dự án chạy độc lập

Ví dụ dành cho thư mục thử nghiệm riêng có Gradle Wrapper 8.5 và JDK 21. Cần mạng để tải plugin/dependency lần đầu. Không thêm Spring Security hay cấu hình quản trị khác vào thí nghiệm này để các kết quả dưới đây chỉ phụ thuộc những thay đổi đang xét.

Cấu trúc các tệp cần tạo:

```text
actuator-conditions/
  settings.gradle
  build.gradle
  gradlew.bat
  gradle/wrapper/...
  src/main/java/demo/ActuatorConditionsApplication.java
  src/main/resources/application.properties
```

`settings.gradle`: 

```groovy
rootProject.name = 'actuator-conditions'
```

`build.gradle`: 

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

`src/main/java/demo/ActuatorConditionsApplication.java`: 

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.actuate.web.exchanges.HttpExchangeRepository;
import org.springframework.boot.actuate.web.exchanges.InMemoryHttpExchangeRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ActuatorConditionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ActuatorConditionsApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }

    @Bean
    @ConditionalOnProperty(name = "demo.exchanges.repository", havingValue = "true")
    public HttpExchangeRepository httpExchangeRepository() {
        return new InMemoryHttpExchangeRepository();
    }
}
```

`src/main/resources/application.properties`: 

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,httpexchanges
```

`demo.exchanges.repository` là thuộc tính tự đặt của ví dụ, không phải thuộc tính có sẵn của Actuator. Khi giá trị là `true`, phương thức `@Bean` cung cấp repository. Khi không khai báo, điều kiện này không khớp.

Đây là ứng dụng Spring Boot đầy đủ khi có các tệp và Wrapper nói trên; không chạy tệp Java bằng một lệnh `javac` thiếu classpath dependency.

### 6.2. Lượt A: đã include nhưng chưa có repository

Trong PowerShell, khởi động:

```powershell
.\gradlew.bat bootRun
```

Đợi ứng dụng khởi động thành công. Trong cửa sổ PowerShell khác:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/httpexchanges
```

Hai dòng stdout kỳ vọng, theo thứ tự:

```text
200
404
```

Kết luận của lượt A: HTTP server và Actuator đang hoạt động; tên `httpexchanges` đã có trong exposure nhưng vẫn thiếu bean cung cấp lịch sử HTTP.

### 6.3. Lượt B: cung cấp repository, giữ nguyên exposure

Dừng ứng dụng bằng Ctrl+C, đợi tiến trình dừng rồi chạy lại:

```powershell
.\gradlew.bat bootRun --args="--demo.exchanges.repository=true"
```

Gọi lần lượt:

```powershell
curl.exe -s http://127.0.0.1:8080/ping
```

Body chính xác của phản hồi `/ping` là `pong` (lệnh trên không thêm ký tự xuống dòng). Sau đó kiểm tra mã HTTP:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/httpexchanges
```

Stdout kỳ vọng:

```text
200
```

Để xem dữ liệu, gọi lại URL trên mà bỏ `-o NUL -w ...`. Nội dung JSON có thông tin các lượt trao đổi đã được ghi; thời điểm, thời lượng và số phần tử phụ thuộc hoạt động thực tế nên không có một chuỗi JSON cố định cho mọi lần chạy.

Kết luận của lượt B: thay đổi quyết định là có bean repository; không cần mở thêm tất cả endpoint.

### 6.4. Lượt C: có repository nhưng tắt endpoint

Dừng lượt B rồi chạy:

```powershell
.\gradlew.bat bootRun --args="--demo.exchanges.repository=true --management.endpoint.httpexchanges.enabled=false"
```

Lặp lại lệnh lấy mã HTTP của `httpexchanges`: kỳ vọng `404`. Bean nền tảng vẫn được khai báo nhưng endpoint bị tắt.

Tiếp tục một lượt độc lập, thay cờ tắt endpoint bằng cờ loại khỏi HTTP:

```powershell
.\gradlew.bat bootRun --args="--demo.exchanges.repository=true --management.endpoints.web.exposure.exclude=httpexchanges"
```

Kỳ vọng cũng `404`, nhưng nguyên nhân cấu hình khác. Hai lượt cho thấy không thể phân biệt thiếu bean, bị tắt hay không được công bố chỉ bằng một mã phản hồi.

Các kết quả trên giả định đúng dự án mẫu, cổng trống, không có proxy, biến môi trường hoặc tệp cấu hình ngoài ghi đè; chúng không phải khẳng định mọi ứng dụng tùy biến đều trả cùng mã.

## 7. Chẩn đoán bằng bằng chứng trong ứng dụng thực

### Kiểm tra địa chỉ trước

Xác nhận ứng dụng đã khởi động và đang lắng nghe. Với HTTP, đối chiếu `management.server.port`, `management.endpoints.web.base-path`, `management.endpoints.web.path-mapping` và đường dẫn gốc của ứng dụng. Cổng quản trị có thể khác cổng nghiệp vụ; `management.server.port=-1` tắt HTTP quản trị. [Cấu hình cổng và đường dẫn quản trị](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

### Đọc báo cáo điều kiện

Khởi động bản JAR thực tế với `--debug` để xem báo cáo điều kiện trong log:

```powershell
java -jar .\app.jar --debug
```

`app.jar` ở đây là tên minh họa, thay bằng tên artifact thực tế. Tìm cấu hình của endpoint và cấu hình tạo bean nền tảng. Đọc nguyên nhân không khớp, không chỉ đếm mục trong nhóm kết quả âm. Xem cả cấu hình bị loại trừ và trường hợp cấu hình nhường chỗ cho bean do ứng dụng khai báo. [Báo cáo tự động cấu hình và cơ chế nhường chỗ](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html).

Ví dụ cách ghi nhận kết luận có thể kiểm chứng:

```text
Quan sát: GET /actuator/httpexchanges trả 404.
Bằng chứng bổ sung: không có bean HttpExchangeRepository.
Giả thuyết: thiếu nguồn dữ liệu cho endpoint.
Thử nghiệm: chỉ thêm repository trong cấu hình phát triển, khởi động lại.
Kiểm tra lại: đối chiếu điều kiện và gọi lại cùng URL.
```

Đây là mẫu suy luận, không phải trích nguyên văn log Spring Boot. Nếu chọn dùng `/actuator/conditions` để xem báo cáo, bản thân endpoint đó cũng phải được bật, công bố và truy cập đúng quyền.

### Phân loại triệu chứng

| Triệu chứng | Hướng kiểm tra tiếp theo |
| --- | --- |
| Không kết nối được | Tiến trình, địa chỉ, cổng, giao thức, mạng |
| `404` | Đường dẫn, bean, enablement, exposure; kiểm tra cả proxy/chính sách tùy biến |
| `401`, `403` hoặc chuyển sang đăng nhập | Xác thực, phân quyền, chuỗi bảo mật thực tế; chưa đủ kết luận endpoint tồn tại |
| `200` nhưng dữ liệu trống | Nguồn dữ liệu, cấu hình ghi nhận, hoạt động đã phát sinh |
| `5xx` | Lỗi thực thi, lỗi thành phần tích hợp, log ngoại lệ |

Bảng này là hướng khoanh vùng, không phải phép suy ngược chắc chắn từ mã HTTP. Bộ lọc bảo mật có thể chặn yêu cầu trước khi tìm handler; proxy cũng có thể thay đổi phản hồi.

## 8. Lỗi thường gặp và cách tự kiểm tra

- **Chỉ thêm exposure:** xác minh dependency lúc chạy và bean nền tảng trước.
- **Có thư viện nhưng không có bean:** xem cấu hình tích hợp, profile đang chạy và cấu hình bị loại trừ.
- **Thấy cấu hình không khớp rồi xóa bean tự khai báo:** đọc xem đó có phải nhánh `@ConditionalOnMissingBean` đang nhường chỗ đúng thiết kế không.
- **Thấy endpoint trả danh sách rỗng rồi tìm cách bật lại:** kiểm tra việc phát sinh và lưu dữ liệu; không đồng nhất dữ liệu trống với endpoint vắng mặt.
- **Sửa tệp cấu hình nhưng không biết giá trị hiệu lực:** kiểm tra các tham số dòng lệnh, biến môi trường và profile đang ghi đè.

Thực hành: với mỗi tình huống, nêu điều kiện cần kiểm tra và bằng chứng sẽ thu thập.

1. `flyway` đã có trong HTTP include; ứng dụng có DataSource nhưng không có bean Flyway.
2. `metrics` trả số đo; dự án không có registry Prometheus.
3. `httpexchanges` có repository và đã include nhưng cũng nằm trong HTTP exclude.
4. `httpexchanges` trả `200`, repository rỗng sau khởi động và ghi nhận HTTP đang bị tắt.

Đối chiếu: (1) thiếu bean tích hợp Flyway; (2) thiếu tích hợp registry cho Prometheus; (3) bị loại khỏi HTTP; (4) endpoint đã truy cập được, cần xét việc ghi dữ liệu. Trong từng trường hợp, chỉ thay đổi điều kiện đang kiểm chứng rồi đo lại, thay vì thay đồng thời dependency, exposure và bảo mật.

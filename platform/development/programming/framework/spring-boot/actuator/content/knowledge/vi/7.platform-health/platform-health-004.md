# Ý nghĩa của UP, DOWN, OUT_OF_SERVICE và UNKNOWN

## 1. Bốn trạng thái trả lời những câu hỏi khác nhau

Khi đọc `/actuator/health`, ta thường nhìn thấy một mã ngắn như `UP` hoặc `DOWN`. Nhưng sức khỏe ứng dụng không chỉ có hai khả năng “còn chạy” và “đã chết”.

Cần phân biệt:

- Điều kiện kiểm tra đang đáp ứng như mong đợi.
- Phép kiểm tra đã xác định một lỗi.
- Thành phần được đưa ra ngoài phục vụ và không nên được sử dụng.
- Chưa xác định được tình trạng của thành phần.

Spring Boot dùng các trạng thái thông dụng tương ứng:

| Trạng thái | Ý nghĩa chính | Câu hỏi giúp lựa chọn |
| --- | --- | --- |
| `UP` | Thành phần hoạt động như mong đợi theo điều kiện đã kiểm tra | Đã có bằng chứng điều kiện cần đang đáp ứng chưa? |
| `DOWN` | Thành phần gặp lỗi ngoài mong đợi | Phép kiểm tra đã xác định điều kiện cần bị thất bại chưa? |
| `OUT_OF_SERVICE` | Thành phần được đưa ra ngoài phục vụ và không nên được dùng | Dù tiến trình còn hoạt động, thành phần có đang bị loại khỏi phục vụ không? |
| `UNKNOWN` | Trạng thái chưa xác định | Có đủ thông tin để kết luận tình trạng hiện tại chưa? |

Đây là ngữ nghĩa các hằng chuẩn của lớp `Status`. [API Status của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/Status.html).

Trạng thái cần được đọc theo **phạm vi phép kiểm tra**. Một thành phần UP không chứng minh mọi luồng nghiệp vụ đều đúng; một thành phần DOWN không chứng minh JVM đã ngừng chạy.

Bài dùng **Java 21, Spring Boot 3.3.13 và Spring MVC** để tạo kết quả có thể tái hiện. Phiên bản được cố định cho ví dụ thuộc dòng 3.3.x, không hàm ý đây là phiên bản mới nhất hoặc khuyến nghị triển khai sản xuất hiện tại.

## 2. Hiểu đúng từng trạng thái

### 2.1. UP: điều kiện đang được kiểm tra đã đáp ứng

Một phép kiểm tra có thể trả UP khi kết nối thử thành công, dung lượng còn trên ngưỡng hoặc một điều kiện nội bộ đã sẵn sàng.

Điều cần hỏi tiếp là **đã kiểm tra điều gì**. Ví dụ, lấy được một kết nối cơ sở dữ liệu không chứng minh:

- mọi câu truy vấn đều chạy đúng;
- dữ liệu nghiệp vụ luôn hợp lệ;
- ứng dụng đủ năng lực xử lý lưu lượng sắp tới;
- các dịch vụ không nằm trong phép kiểm tra cũng đang khỏe.

UP là kết quả tích cực trong phạm vi đã định nghĩa. Không nên trả UP chỉ vì đoạn kiểm tra chưa được viết xong hoặc để làm cho cảnh báo biến mất.

### 2.2. DOWN: đã xác định được điều kiện thất bại

Giả sử hợp đồng của một phép kiểm tra là “có thể kết nối tới phụ thuộc cần thiết trong giới hạn thời gian”. Nếu thao tác đó thất bại, trả DOWN có thể là lựa chọn phù hợp.

DOWN nói về **kết quả kiểm tra sức khỏe**, không trực tiếp nói về vòng đời tiến trình. Ứng dụng vẫn có thể nhận một yêu cầu health, thực hiện kiểm tra và trả:

```json
{"status":"DOWN"}
```

Trong trường hợp đó, chính việc nhận được phản hồi cho thấy đường xử lý health vẫn hoạt động đủ để báo kết quả. Phải tìm nguyên nhân của điều kiện thất bại, thay vì chỉ suy ra “Java đã chết”.

Cũng không nên tự động kết luận rằng mọi DOWN đều được sửa bằng khởi động lại ứng dụng. Một phụ thuộc từ xa ngừng hoạt động không được phục hồi chỉ nhờ khởi động lại phía gọi.

### 2.3. OUT_OF_SERVICE: không nên sử dụng thành phần này để phục vụ

OUT_OF_SERVICE biểu diễn việc thành phần đang ở ngoài phục vụ. Một tình huống thiết kế thường gặp là chủ động ngừng nhận công việc mới trong một đợt bảo trì hoặc giai đoạn chuyển trạng thái.

Điểm khác với DOWN nằm ở **ý nghĩa tín hiệu**:

| Tình huống minh họa | Trạng thái phù hợp để xem xét |
| --- | --- |
| Một phép kiểm tra quan trọng vừa xác định lỗi bất ngờ | DOWN |
| Thành phần chủ động được đưa ra ngoài phục vụ theo chính sách vận hành | OUT_OF_SERVICE |

Đây không phải quy tắc rằng chỉ bảo trì mới được dùng OUT_OF_SERVICE. Ý nghĩa cốt lõi là thành phần không nên được sử dụng để phục vụ; điều kiện cụ thể do thiết kế của hệ thống quyết định.

Việc tạo `Health.outOfService()` **chỉ tạo báo cáo sức khỏe**. Nó không tự đóng cổng HTTP, ngắt mọi kết nối, dừng nhận tác vụ hay làm bộ cân bằng tải chuyển hướng. Những hành vi đó cần cơ chế riêng đọc và thực thi chính sách phù hợp.

Spring Boot cũng có mô hình sẵn sàng nhận lưu lượng và indicator riêng cho trạng thái sẵn sàng. Không đồng nhất mọi báo cáo health với toàn bộ cơ chế điều khiển lưu lượng. [Mô hình khả dụng của ứng dụng](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability), [ReadinessStateHealthIndicator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/availability/ReadinessStateHealthIndicator.html).

### 2.4. UNKNOWN: chưa đủ cơ sở xác định tình trạng

UNKNOWN là một kết quả sức khỏe có ý nghĩa, không phải một giá trị bị thiếu trong JSON. Ví dụ, một phép kiểm tra chưa có kết quả có thể được thiết kế để trả UNKNOWN.

Cần phân biệt ba trường hợp:

| Quan sát | Điều có thể kết luận |
| --- | --- |
| Có phản hồi `status=UNKNOWN` | Thành phần đã trả một trạng thái chưa xác định |
| Không có thành phần tại đường dẫn được hỏi | Không có tài nguyên contributor đó để trả kết quả |
| Không kết nối được tới ứng dụng | Chưa nhận được phản hồi health để biết trạng thái |

Không dùng UNKNOWN như một cách làm nhẹ mọi lỗi. Nếu hợp đồng kiểm tra đã xác định việc kết nối thất bại là lỗi sức khỏe, bắt lỗi rồi luôn trả UNKNOWN sẽ che mất ý nghĩa đó.

Với một lần hết thời gian chờ, cần xác định rõ hợp đồng kiểm tra: thời gian chờ có phải là điều kiện thất bại không, hay phép đo thực sự chưa cho phép kết luận? Đừng chọn trạng thái chỉ dựa trên tên ngoại lệ hoặc mong muốn tránh cảnh báo.

## 3. Trạng thái của lá và trạng thái tổng hợp không giống nhau

Một indicator trả trạng thái cho thành phần của nó. Khi nhiều thành phần cùng tham gia, bộ tổng hợp quyết định trạng thái cho toàn bộ phạm vi được hỏi.

Với `SimpleStatusAggregator` mặc định trong Spring Boot 3.3.13, thứ tự ưu tiên là:

```text
DOWN -> OUT_OF_SERVICE -> UP -> UNKNOWN
```

Trạng thái được nhận diện đứng sớm nhất trong danh sách quyết định kết quả. [Cách tổng hợp mặc định ở phiên bản 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.java).

| Các trạng thái thành phần | Trạng thái tổng hợp mặc định |
| --- | --- |
| UP và UP | UP |
| DOWN và UP | DOWN |
| OUT_OF_SERVICE và UP | OUT_OF_SERVICE |
| DOWN và OUT_OF_SERVICE | DOWN |
| UNKNOWN và UP | UP |
| UNKNOWN và OUT_OF_SERVICE | OUT_OF_SERVICE |
| Chỉ UNKNOWN | UNKNOWN |

Các hệ quả cần hiểu:

- DOWN không bị nhiều UP “biểu quyết thắng”.
- OUT_OF_SERVICE và DOWN vẫn có ý nghĩa riêng dù đều có thể làm gốc không phục vụ.
- UNKNOWN không đứng trên UP trong thứ tự mặc định.
- Một trạng thái gốc UP có thể đi cùng một thành phần UNKNOWN.

Nếu muốn UNKNOWN ảnh hưởng mạnh hơn UP, cần chủ động thay chính sách, không chỉ đổi cách giải thích bằng lời. Trong bài thực hành, ta sẽ kiểm tra cả thứ tự mặc định và một thứ tự tùy chỉnh.

## 4. Ý nghĩa trạng thái không phải ý nghĩa mã HTTP

Trong ánh xạ HTTP mặc định của Spring Boot 3.3:

| Trạng thái health của phạm vi được hỏi | HTTP mặc định |
| --- | --- |
| UP | 200 |
| DOWN | 503 |
| OUT_OF_SERVICE | 503 |
| UNKNOWN | 200 |

DOWN và OUT_OF_SERVICE có cùng mã HTTP mặc định nhưng mang thông tin vận hành khác nhau. Ngược lại, UP và UNKNOWN đều có thể trả 200, nhưng không có cùng mức độ hiểu biết về tình trạng thành phần. [Ánh xạ trạng thái health sang HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-healthindicators).

Có ba quyết định độc lập:

```text
Điều kiện quan sát
    -> Indicator chọn trạng thái
    -> Bộ tổng hợp chọn trạng thái của nhóm/toàn bộ
    -> Bộ ánh xạ chọn mã HTTP
```

Đổi thứ tự ưu tiên để gốc trở thành UNKNOWN không tự làm HTTP đổi thành 503. Cũng không nên diễn giải HTTP 503 của health thành một ngoại lệ xử lý HTTP hoặc một tiến trình đã dừng.

Ngoài ra, 401/403 do kiểm soát truy cập, 404 do không tìm thấy tài nguyên hoặc lỗi kết nối mạng là các tình huống khác. Phải đọc mã HTTP cùng nội dung phản hồi và ngữ cảnh yêu cầu.

## 5. Cách biểu diễn trong Java và JSON

Trong Java, `Status` là một lớp giá trị, không phải một `enum` chỉ có đúng bốn phần tử. Các hằng chuẩn giúp biểu đạt những trường hợp thông dụng; API còn cho phép mã trạng thái riêng.

Các cách tạo kết quả thường dùng là:

```java
Health.up().build();
Health.down().build();
Health.outOfService().build();
Health.unknown().build();
```

Đây là các biểu thức minh họa bên trong mã có sử dụng API `Health`, không phải một chương trình Java độc lập.

Khi trả qua endpoint, mã như `OUT_OF_SERVICE` xuất hiện trong trường JSON `status`. Một `details` đi kèm chỉ bổ sung thông tin giải thích; nó không tự thay thế trạng thái.

Không dùng chỉ số thứ tự kiểu `ordinal()` để so sánh mức độ nghiêm trọng. Mức độ ưu tiên do bộ tổng hợp quy định, không đến từ thứ tự khai báo các hằng trong lớp.

Nếu tạo mã riêng, cần định nghĩa ngữ nghĩa, thứ tự tổng hợp và ánh xạ HTTP tương ứng. Bài này tập trung bốn trạng thái chuẩn để xây dựng cách đọc nhất quán.

## 6. Ví dụ chạy được: phân biệt lỗi phụ thuộc với chủ trương nhận việc

Dự án có hai kiểm tra **mô phỏng** độc lập:

- `dependency`: kết quả kiểm tra phụ thuộc là PASS, FAIL hoặc NOT_RUN.
- `admission`: trạng thái báo cáo về chủ trương nhận công việc là true hoặc false.

Quy tắc do bài tự thiết kế:

| Đầu vào mô phỏng | Trạng thái của indicator |
| --- | --- |
| dependency PASS | UP |
| dependency FAIL | DOWN |
| dependency NOT_RUN | UNKNOWN |
| admission true | UP |
| admission false | OUT_OF_SERVICE |

PASS/FAIL/NOT_RUN là các giá trị đầu vào riêng của ví dụ, không phải mã health chuẩn của Spring Boot.

Không có kiểm tra cơ sở dữ liệu thật và không có cổng điều khiển nhận việc thật trong dự án. Mục tiêu là quan sát đúng ngữ nghĩa và cách kết hợp bốn trạng thái mà không cần một sự cố bên ngoài.

Cấu trúc:

```text
standard-health-status-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/statuslab/
    │   │   ├── StatusLabApplication.java
    │   │   └── DemoStatusIndicators.java
    │   └── resources/application.yml
    └── test/java/com/example/statuslab/
        └── StandardHealthStatusesTest.java
```

Dùng Maven với JDK 21; lần dựng đầu cần tải thư viện từ kho Maven. Các lớp cần Spring Boot nên không chạy riêng bằng `javac TenLop.java`.

### 6.1. pom.xml

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
    <groupId>com.example</groupId>
    <artifactId>standard-health-status-lab</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

### 6.2. src/main/resources/application.yml

```yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  jmx:
    enabled: false

management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: health
      discovery:
        enabled: false
    jmx:
      exposure:
        exclude: "*"
  endpoint:
    health:
      enabled: true
      show-components: always
      show-details: always
  health:
    defaults:
      enabled: false

demo:
  probe-result: PASS
  accepting-work: true
```

Ứng dụng chỉ lắng nghe trên `127.0.0.1` và chỉ đưa health ra HTTP. Không có Spring Security trong dự án cục bộ này.

Hai cấu hình dành riêng cho việc học:

- Hiện cả thành phần và chi tiết để đối chiếu từng trạng thái.
- Tắt các kiểm tra tự cấu hình mặc định để phản hồi chỉ chứa hai kiểm tra mô phỏng, không phụ thuộc đĩa hoặc thư viện của máy chạy.

Không dùng việc tắt kiểm tra mặc định như một cấu hình vận hành chung. Với ứng dụng thật, phải chọn các kiểm tra có giá trị và giới hạn quyền xem dữ liệu chi tiết.

### 6.3. StatusLabApplication.java

Đặt tại `src/main/java/com/example/statuslab/StatusLabApplication.java`.

```java
package com.example.statuslab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StatusLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(StatusLabApplication.class, args);
    }
}
```

### 6.4. DemoStatusIndicators.java

Đặt tại `src/main/java/com/example/statuslab/DemoStatusIndicators.java`.

```java
package com.example.statuslab;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class DemoStatusIndicators {
    public enum ProbeResult {
        PASS, FAIL, NOT_RUN
    }

    @Bean
    HealthIndicator dependencyHealthIndicator(
            @Value("${demo.probe-result}") ProbeResult result) {
        return () -> {
            Health.Builder builder = switch (result) {
                case PASS -> Health.up();
                case FAIL -> Health.down();
                case NOT_RUN -> Health.unknown();
            };
            return builder.withDetail("probeResult", result.name()).build();
        };
    }

    @Bean
    HealthIndicator admissionHealthIndicator(
            @Value("${demo.accepting-work}") boolean acceptingWork) {
        return () -> (acceptingWork ? Health.up() : Health.outOfService())
                .withDetail("acceptingWork", acceptingWork)
                .build();
    }
}
```

Hai bean xuất hiện trong JSON với tên `dependency` và `admission`: tên bean được bỏ hậu tố `HealthIndicator`.

`ProbeResult` là một enum do bài tự định nghĩa để mô phỏng đầu vào. Nó không làm cho lớp `Status` của Spring Boot trở thành enum.

Phần `details.probeResult` giúp biết đầu vào đã dẫn tới kết quả nào. `details.acceptingWork` giải thích trạng thái báo cáo của admission. Hai trường này không tự gây ra việc ngừng phục vụ; chính mã Java chọn UP hoặc OUT_OF_SERVICE.

## 7. Chạy và đọc bốn trạng thái trong tình huống cụ thể

### 7.1. Trạng thái ban đầu

Tại thư mục chứa `pom.xml`, dùng PowerShell với `JAVA_HOME` trỏ đến JDK 21:

```powershell
mvn spring-boot:run
```

Từ terminal thứ hai:

```powershell
curl.exe -s -i -H "Accept: application/json" http://127.0.0.1:8080/actuator/health
```

Mã HTTP là 200. Nội dung JSON tương đương:

```json
{
  "status": "UP",
  "components": {
    "dependency": {
      "status": "UP",
      "details": {
        "probeResult": "PASS"
      }
    },
    "admission": {
      "status": "UP",
      "details": {
        "acceptingWork": true
      }
    }
  }
}
```

Không dựa vào thứ tự các trường hoặc cách xuống dòng của JSON. Điều cần đối chiếu là trạng thái của từng thành phần và của gốc.

### 7.2. FAIL dẫn tới DOWN

Dừng ứng dụng bằng Ctrl+C, rồi chạy lại:

```powershell
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.probe-result=FAIL"
```

Kết quả:

| Phạm vi | Trạng thái | HTTP mặc định |
| --- | --- | --- |
| dependency | DOWN | 503 |
| admission | UP | 200 |
| Gốc | DOWN | 503 |

Ở đây, một phép kiểm tra đã xác định thất bại. Thành phần còn lại UP không xóa được kết quả DOWN.

### 7.3. Chủ động không nhận việc dẫn tới OUT_OF_SERVICE

Dừng và chạy lại:

```powershell
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.probe-result=PASS --demo.accepting-work=false"
```

Kết quả:

| Phạm vi | Trạng thái | HTTP mặc định |
| --- | --- | --- |
| dependency | UP | 200 |
| admission | OUT_OF_SERVICE | 503 |
| Gốc | OUT_OF_SERVICE | 503 |

Hãy gọi riêng từng phạm vi:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health/dependency
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health/admission
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health
```

Kết quả theo thứ tự:

```text
200
503
503
```

Phản hồi của admission có nội dung tương đương:

```json
{
  "status": "OUT_OF_SERVICE",
  "details": {
    "acceptingWork": false
  }
}
```

Ứng dụng vẫn trả được health. Trong ví dụ này, cờ `accepting-work` chỉ được indicator đọc để báo cáo; không có mã điều khiển một bộ nhận tác vụ hay bộ cân bằng tải thật.

### 7.4. Chưa chạy kiểm tra dẫn tới UNKNOWN

Dừng và chạy lại:

```powershell
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.probe-result=NOT_RUN --demo.accepting-work=true"
```

Gọi:

```powershell
curl.exe -s -H "Accept: application/json" http://127.0.0.1:8080/actuator/health/dependency
curl.exe -s -H "Accept: application/json" http://127.0.0.1:8080/actuator/health
```

Ở lá dependency:

```json
{
  "status": "UNKNOWN",
  "details": {
    "probeResult": "NOT_RUN"
  }
}
```

Mã HTTP của lá vẫn là 200. Ở gốc, trạng thái là UP vì admission UP đứng trước UNKNOWN trong thứ tự mặc định.

Điều này không chứng minh phép kiểm tra phụ thuộc đã thành công. Nó chứng minh **UNKNOWN đã được tổng hợp theo chính sách mặc định**.

Nếu cùng lúc đặt `accepting-work=false`, admission sẽ OUT_OF_SERVICE và trạng thái gốc trở thành OUT_OF_SERVICE.

### 7.5. Lỗi và ngừng phục vụ cùng xuất hiện

Dừng và chạy lại:

```powershell
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.probe-result=FAIL --demo.accepting-work=false"
```

Dependency DOWN, admission OUT_OF_SERVICE và trạng thái gốc DOWN. Hai tín hiệu vẫn được giữ ở các thành phần; gốc chọn DOWN vì mức ưu tiên mặc định.

Nếu chỉ xem gốc, ta không biết hết mọi điều kiện con đang đồng thời xảy ra. Khi có quyền xem, các thành phần và chi tiết giúp phân biệt nguyên nhân. [Phạm vi gốc và phạm vi thành phần của Health API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

### 7.6. Đặt UNKNOWN trước UP là một thay đổi chính sách

Có thể thử một thứ tự khác:

```powershell
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.probe-result=NOT_RUN --management.endpoint.health.status.order=down,out-of-service,unknown,up"
```

Gốc lúc này là UNKNOWN thay vì UP, nhưng HTTP vẫn 200 do chưa thay ánh xạ cho UNKNOWN.

Nếu một hệ thống cần coi việc chưa xác định là không đủ điều kiện phục vụ, nó phải thiết kế và kiểm chứng đầy đủ chính sách tổng hợp, mã HTTP và cách bên tiêu thụ phản ứng. Không chỉ đổi thứ tự rồi giả định mọi lớp còn lại đã tự hiểu cùng một ý nghĩa.

Tất cả lệnh khởi động trong các mục trên là những phiên chạy thay thế nhau. Dừng phiên cũ trước khi dùng lại cổng 8080.

## 8. Kiểm thử ngữ nghĩa bằng kết quả quan sát được

Đặt tệp sau tại `src/test/java/com/example/statuslab/StandardHealthStatusesTest.java`.

Kiểm thử dùng `WebApplicationContextRunner` tạo ngữ cảnh cho từng bộ đầu vào và nạp `application.yml`. MockMvc gọi phần xử lý HTTP của Spring MVC mà không cần mở cổng mạng thật.

```java
package com.example.statuslab;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

class StandardHealthStatusesTest {
    private final ObjectMapper json = new ObjectMapper();

    private WebApplicationContextRunner application(String... properties) {
        return new WebApplicationContextRunner()
                .withInitializer(new ConfigDataApplicationContextInitializer())
                .withUserConfiguration(StatusLabApplication.class)
                .withPropertyValues(properties);
    }

    @ParameterizedTest
    @CsvSource({
            "PASS, true, UP, UP, 200",
            "FAIL, true, DOWN, DOWN, 503",
            "NOT_RUN, true, UNKNOWN, UP, 200",
            "PASS, false, UP, OUT_OF_SERVICE, 503",
            "FAIL, false, DOWN, DOWN, 503",
            "NOT_RUN, false, UNKNOWN, OUT_OF_SERVICE, 503"
    })
    void standardStatusesRemainDistinct(
            String probeResult, boolean acceptingWork, String dependencyStatus,
            String overallStatus, int overallHttp) {
        application(
                "demo.probe-result=" + probeResult,
                "demo.accepting-work=" + acceptingWork).run(context -> {
            MockMvc mvc = MockMvcBuilders
                    .webAppContextSetup(context.getSourceApplicationContext())
                    .build();

            var root = mvc.perform(get("/actuator/health"))
                    .andReturn().getResponse();
            assertThat(root.getStatus()).isEqualTo(overallHttp);
            JsonNode body = json.readTree(root.getContentAsString());
            assertThat(body.path("status").asText()).isEqualTo(overallStatus);
            assertThat(body.at("/components/dependency/status").asText())
                    .isEqualTo(dependencyStatus);
            assertThat(body.at("/components/admission/status").asText())
                    .isEqualTo(acceptingWork ? "UP" : "OUT_OF_SERVICE");

            var dependency = mvc.perform(get("/actuator/health/dependency"))
                    .andReturn().getResponse();
            assertThat(dependency.getStatus())
                    .isEqualTo(dependencyStatus.equals("DOWN") ? 503 : 200);
            JsonNode dependencyBody = json.readTree(
                    dependency.getContentAsString());
            assertThat(dependencyBody.path("status").asText())
                    .isEqualTo(dependencyStatus);
            assertThat(dependencyBody.at("/details/probeResult").asText())
                    .isEqualTo(probeResult);

            var admission = mvc.perform(get("/actuator/health/admission"))
                    .andReturn().getResponse();
            assertThat(admission.getStatus()).isEqualTo(acceptingWork ? 200 : 503);
        });
    }

    @Test
    void unknownIsAResultAndNotAMissingEndpoint() {
        application("demo.probe-result=NOT_RUN").run(context -> {
            MockMvc mvc = MockMvcBuilders
                    .webAppContextSetup(context.getSourceApplicationContext())
                    .build();
            var unknown = mvc.perform(get("/actuator/health/dependency"))
                    .andReturn().getResponse();
            assertThat(unknown.getStatus()).isEqualTo(200);
            assertThat(json.readTree(unknown.getContentAsString())
                    .path("status").asText()).isEqualTo("UNKNOWN");
            assertThat(mvc.perform(get("/actuator/health/missing"))
                    .andReturn().getResponse().getStatus()).isEqualTo(404);
        });
    }

    @Test
    void changingSeverityOrderDoesNotAutomaticallyChangeHttpMapping() {
        application(
                "demo.probe-result=NOT_RUN",
                "management.endpoint.health.status.order=down,out-of-service,unknown,up")
                .run(context -> {
                    MockMvc mvc = MockMvcBuilders
                            .webAppContextSetup(context.getSourceApplicationContext())
                            .build();
                    var response = mvc.perform(get("/actuator/health"))
                            .andReturn().getResponse();
                    assertThat(response.getStatus()).isEqualTo(200);
                    assertThat(json.readTree(response.getContentAsString())
                            .path("status").asText()).isEqualTo("UNKNOWN");
                });
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```powershell
mvn test
```

Phần kết quả thành công cần thấy:

```text
Tests run: 8, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Sáu bộ tham số kiểm tra các tổ hợp của hai indicator. Hai kiểm thử còn lại phân biệt UNKNOWN với tài nguyên không tồn tại và chứng minh thay thứ tự tổng hợp không tự đổi mã HTTP.

Các bằng chứng quan trọng:

- UP, DOWN, OUT_OF_SERVICE và UNKNOWN vẫn hiện đúng ở từng thành phần.
- DOWN và OUT_OF_SERVICE không bị gộp thành cùng một nội dung chỉ vì cùng trả 503.
- UNKNOWN không bị coi là UP ở chính thành phần đó, dù trạng thái gốc có thể UP.
- UNKNOWN có thể là một phản hồi hợp lệ với HTTP 200; tài nguyên không có mới là trường hợp khác.
- Chính sách tùy chỉnh phải được đánh giá theo cả trạng thái gốc và mã HTTP.

Log khởi tạo và thời gian chạy có thể khác giữa các máy. Kiểm thử trong ứng dụng này không xác minh TLS, tường lửa hoặc cách một bộ cân bằng tải thật tiêu thụ health.

## 9. Chọn trạng thái có căn cứ trong ứng dụng thật

Một hợp đồng kiểm tra cần mô tả điều kiện quan sát, bằng chứng thành công, bằng chứng thất bại và cách xử lý khi chưa thể kết luận hoặc đang ngoài phục vụ.

Ví dụ với một phép kiểm tra phụ thuộc:

| Nội dung cần xác định | Ví dụ thiết kế |
| --- | --- |
| Phạm vi | Có thể thực hiện thao tác kiểm tra nhẹ đã chọn trên phụ thuộc trong giới hạn thời gian |
| Thành công | Thao tác đáp ứng điều kiện đã định nghĩa |
| Thất bại | Không đáp ứng điều kiện đó, gồm các trường hợp lỗi hoặc hết hạn đã được quy ước |
| Chưa xác định | Chưa có phép đo hợp lệ để kết luận, nếu thiết kế thực sự có trạng thái này |
| Ngoài phục vụ | Thành phần đang được loại khỏi phục vụ theo chính sách áp dụng |

Không bắt buộc một indicator phải sử dụng đủ cả bốn trạng thái. Nếu hợp đồng chỉ có thành công hoặc thất bại rõ ràng, việc cố thêm UNKNOWN có thể làm tín hiệu khó hiểu hơn.

Ngoài trạng thái của từng indicator, cần thống nhất với bên tiêu thụ:

- Bên giám sát xem HTTP, JSON hay cả hai?
- Có đọc health gốc hay một nhóm/phạm vi cụ thể?
- UNKNOWN được chấp nhận, cảnh báo hay coi là không đủ điều kiện?
- Ai điều khiển việc đưa thành phần ra hoặc vào phục vụ?
- Bằng chứng nào giúp giải thích sự chuyển trạng thái?

Thông tin chi tiết phục vụ chẩn đoán nên hữu ích nhưng không chứa bí mật hoặc dữ liệu nghiệp vụ không cần thiết. Không đưa mật khẩu, token hay toàn bộ phản hồi nhạy cảm của phụ thuộc vào details.

## 10. Những lỗi diễn giải thường gặp

| Hiểu nhầm | Cách đọc đúng |
| --- | --- |
| UP nghĩa là không thể có lỗi nghiệp vụ | UP chỉ phản ánh điều kiện và phạm vi đã kiểm tra |
| DOWN nghĩa là tiến trình đã thoát | Một tiến trình đang chạy vẫn có thể báo DOWN |
| OUT_OF_SERVICE chỉ là tên khác của DOWN | Một trạng thái biểu đạt ngoài phục vụ; trạng thái kia biểu đạt lỗi đã xác định |
| OUT_OF_SERVICE tự đóng cổng hoặc chuyển hướng lưu lượng | Nó là báo cáo; cơ chế tiêu thụ và thực thi phải được thiết kế riêng |
| UNKNOWN nghĩa là không có endpoint | UNKNOWN là một kết quả của thành phần; tài nguyên không tồn tại là tình huống khác |
| UNKNOWN mặc nhiên an toàn hoặc mặc nhiên là lỗi nghiêm trọng nhất | Phải đọc hợp đồng kiểm tra và chính sách tổng hợp |
| Nhiều UP sẽ làm gốc UP dù có DOWN | Bộ tổng hợp mặc định dùng thứ tự ưu tiên, không tính đa số |
| HTTP 200 luôn nghĩa là UP | UNKNOWN cũng mặc định có thể trả HTTP 200 |
| Hai trạng thái cùng HTTP 503 có cùng ý nghĩa | DOWN và OUT_OF_SERVICE vẫn giúp phân biệt tình huống |
| Đổi thứ tự tổng hợp tự đổi HTTP | Hai cơ chế được cấu hình và kiểm chứng riêng |
| Đổi chữ trong details sẽ làm framework đổi trạng thái | Indicator phải chọn trạng thái; details chỉ giải thích |
| Phải dùng đủ bốn trạng thái trong mọi indicator | Chỉ dùng các trạng thái mà hợp đồng kiểm tra có thể giải thích rõ |

## 11. Thực hành phân loại tình huống

Với thứ tự và ánh xạ mặc định, hãy dự đoán trước:

1. Phép kiểm tra phụ thuộc thất bại, nhưng chủ trương nhận việc vẫn bật.
2. Phụ thuộc đáp ứng, nhưng thành phần được đưa ra ngoài phục vụ.
3. Chưa có kết quả kiểm tra phụ thuộc, còn admission UP.
4. Chưa có kết quả kiểm tra phụ thuộc, còn admission OUT_OF_SERVICE.
5. Cùng có lỗi phụ thuộc và admission OUT_OF_SERVICE.

Đối chiếu theo mô hình bài thực hành:

| Tình huống | dependency | admission | Gốc | HTTP gốc |
| --- | --- | --- | --- | --- |
| 1 | DOWN | UP | DOWN | 503 |
| 2 | UP | OUT_OF_SERVICE | OUT_OF_SERVICE | 503 |
| 3 | UNKNOWN | UP | UP | 200 |
| 4 | UNKNOWN | OUT_OF_SERVICE | OUT_OF_SERVICE | 503 |
| 5 | DOWN | OUT_OF_SERVICE | DOWN | 503 |

Câu hỏi tiếp theo: nếu chỉ lưu HTTP gốc mà bỏ nội dung JSON, thông tin nào bị mất?

Ta không phân biệt được UP với UNKNOWN chỉ từ HTTP 200, cũng không phân biệt được DOWN với OUT_OF_SERVICE chỉ từ HTTP 503. Còn nếu chỉ lưu trạng thái gốc, ta có thể không thấy những trạng thái con đồng thời tồn tại.

Cách đọc có căn cứ là đi theo chuỗi: **điều kiện nào được kiểm tra → trạng thái nào do thành phần trả → chính sách nào tổng hợp → mã HTTP nào được ánh xạ → bên tiêu thụ sẽ làm gì**.

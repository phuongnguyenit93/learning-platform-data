# Ánh xạ trạng thái sức khỏe sang HTTP status bằng HttpCodeStatusMapper

## 1. Hai kết quả cần đọc khi gọi health

Khi gọi `/actuator/health`, ta nhận đồng thời **trạng thái sức khỏe trong phần thân JSON** và **mã trạng thái HTTP của phản hồi**. Hai giá trị này phục vụ hai đối tượng khác nhau:

- Con người hoặc chương trình đọc JSON dùng `UP`, `DOWN` hay một trạng thái tùy chỉnh để hiểu tình trạng ứng dụng.
- Bộ giám sát hoặc bộ cân bằng tải có thể chỉ đọc mã HTTP để quyết định lần kiểm tra có thành công hay không.

Ví dụ, một ứng dụng báo `{"status":"DOWN"}` nhưng trả HTTP `200` có thể vẫn được hệ thống chỉ kiểm tra mã HTTP xem là thành công. Muốn hiểu và cấu hình đúng hành vi này, cần biết bước chuyển từ `Status` sang mã HTTP.

Trong Spring Boot Actuator, `HttpCodeStatusMapper` đảm nhiệm bước chuyển đó. Bài sử dụng API Spring Boot **3.3.x**, ví dụ chạy với **JDK 21** và phụ thuộc **3.3.0** để cố định kết quả; đây là phiên bản minh họa, không phải yêu cầu nâng hoặc hạ phiên bản dự án đang có.

### 1.1. Vị trí của mapper trong luồng xử lý

Với một phản hồi health hợp lệ ở đường dẫn tổng hoặc một nhóm, có thể hình dung:

```text
HealthIndicator
    -> Health chứa Status của từng thành phần
    -> StatusAggregator chọn Status tổng hợp
    -> HttpCodeStatusMapper chuyển Status đó thành mã HTTP
    -> phản hồi: mã HTTP + dữ liệu Health
```

| Thành phần | Câu hỏi cần trả lời | Ví dụ kết quả |
| --- | --- | --- |
| `HealthIndicator` | Thành phần được kiểm tra đang ở trạng thái nào? | `Health` có `Status.DOWN` |
| `StatusAggregator` | Khi nhiều thành phần có trạng thái khác nhau, trạng thái tổng là gì? | `DOWN` |
| `HttpCodeStatusMapper` | Với trạng thái đã chọn, HTTP cần trả mã nào? | `503` |

Mapper không kiểm tra cơ sở dữ liệu, không lựa chọn thành phần thuộc nhóm và không thay đổi trạng thái tổng hợp. Trong lớp mở rộng HTTP của health, Spring Boot lấy mapper của nhóm tương ứng, truyền vào `health.getStatus()` và dùng số nguyên trả về làm mã HTTP. [Mã nguồn HealthEndpointWebExtension 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointWebExtension.java)

**Hệ quả khi xử lý lỗi:** nếu JSON đang là `UP` trong khi bạn mong `DEGRADED`, hãy kiểm tra kết quả các indicator và cách tổng hợp trước. Thêm ánh xạ `DEGRADED -> 503` không giúp ích nếu mapper thực tế chỉ nhận `UP`.

## 2. Hợp đồng của HttpCodeStatusMapper và mặc định

### 2.1. Đầu vào là Status, đầu ra là int

Chữ ký phương thức cần quan tâm:

```java
int getStatusCode(Status status);
```

`Status` là đối tượng của hệ thống health, không phải `org.springframework.http.HttpStatus`. Ta lấy mã sức khỏe bằng `status.getCode()`, chẳng hạn `"DOWN"`. Giá trị trả về là số như `200` hoặc `503`.

Các kiểu dùng trong bài đều thuộc gói:

```java
import org.springframework.boot.actuate.health.HttpCodeStatusMapper;
import org.springframework.boot.actuate.health.SimpleHttpCodeStatusMapper;
import org.springframework.boot.actuate.health.Status;
```

Có thể triển khai mapper bằng lambda. `HttpCodeStatusMapper.DEFAULT` cung cấp mapper mặc định, còn `SimpleHttpCodeStatusMapper` triển khai ánh xạ dựa trên một bảng. [API và các nơi sử dụng HttpCodeStatusMapper 3.3.13](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/class-use/HttpCodeStatusMapper.html)

### 2.2. Bảng mặc định

| Trạng thái truyền vào mapper mặc định | HTTP trả về |
| --- | --- |
| `DOWN` | `503` |
| `OUT_OF_SERVICE` | `503` |
| `UP` | `200` |
| `UNKNOWN` | `200` |
| Trạng thái khác chưa có ánh xạ | `200` |

`UNKNOWN` có nghĩa là chưa xác định được trạng thái; nó không đồng nghĩa với `UP` dù cùng nhận HTTP `200` theo mặc định. [Ý nghĩa các hằng Status](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/Status.html)

Quy tắc dự phòng về `200` là một chính sách ánh xạ, không phải bằng chứng ứng dụng đã khỏe. Nếu hệ thống vận hành yêu cầu `UNKNOWN` phải bị xem là không sẵn sàng, cần khai báo chính sách đó rõ ràng.

## 3. Cấu hình bảng ánh xạ bằng properties

Với yêu cầu chỉ phụ thuộc mã sức khỏe, cấu hình thường dễ đọc và bảo trì hơn viết một bean. Ví dụ hệ thống định nghĩa `DEGRADED` là vẫn chạy nhưng không đáp ứng chất lượng cần thiết để nhận lưu lượng.

```properties
management.endpoint.health.status.http-mapping.down=503
management.endpoint.health.status.http-mapping.out-of-service=503
management.endpoint.health.status.http-mapping.degraded=503
```

Nếu muốn `UNKNOWN` cũng trả `503`, thêm:

```properties
management.endpoint.health.status.http-mapping.unknown=503
```

Dùng các khóa cấu hình theo dạng chữ thường và dấu gạch nối như ví dụ, trong khi hằng Java vẫn là `Status.OUT_OF_SERVICE` và mã JSON là `"OUT_OF_SERVICE"`.

### 3.1. Bẫy: bảng tùy chỉnh thay bảng mặc định

Cấu hình sau **chưa đủ** để bảo toàn hành vi `DOWN -> 503`:

```properties
management.endpoint.health.status.http-mapping.degraded=503
```

Khi có bảng tùy chỉnh, không được hiểu rằng Spring Boot tự thêm từng mục đó vào bảng mặc định. Nếu cần giữ `DOWN` và `OUT_OF_SERVICE` trả `503`, phải khai báo lại cả hai. Các mã chưa có trong bảng tùy chỉnh tiếp tục dùng giá trị dự phòng `200`. Đây là hành vi được tài liệu Spring Boot 3.3 mô tả rõ. [Cấu hình HTTP mapping của health](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-health-indicators)

Đối chiếu trực tiếp trên `SimpleHttpCodeStatusMapper`:

```java
HttpCodeStatusMapper mapper =
        new SimpleHttpCodeStatusMapper(Map.of("degraded", 503));

System.out.println(mapper.getStatusCode(Status.DOWN)); // 200
System.out.println(mapper.getStatusCode(new Status("DEGRADED"))); // 503
```

Đây là đoạn trích, cần import `java.util.Map` và các kiểu health. Constructor nhận bảng không tự thêm các mục mặc định vào bảng đó; constructor không tham số tạo mapper dùng mặc định. [API SimpleHttpCodeStatusMapper 3.3.13](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleHttpCodeStatusMapper.html)

### 3.2. Ánh xạ và thứ tự mức độ là hai cấu hình độc lập

Để một trạng thái tùy chỉnh tham gia tổng hợp theo ý định, cần cấu hình thứ tự phù hợp, ví dụ:

```properties
management.endpoint.health.status.order=down,out-of-service,degraded,up,unknown
```

Trong thứ tự này, `DEGRADED` được chọn trước `UP` nếu cùng xuất hiện. Việc đặt `UNKNOWN` sau `UP` là lựa chọn của ví dụ; nếu cần ưu tiên trạng thái chưa xác định, hãy đặt nó trước `UP`.

Đây là **toàn bộ thứ tự bạn muốn dùng**, không phải một mục thêm vào danh sách mặc định. Hãy giữ cả những trạng thái chuẩn mà ứng dụng cần tổng hợp.

Nếu để bộ tổng hợp mặc định gặp tập `{UP, DEGRADED}`, `DEGRADED` không nằm trong thứ tự mặc định nên không thắng được `UP`. Khi chỉ có trạng thái không được nhận biết trong thứ tự, kết quả tổng hợp có thể là `UNKNOWN`. Vì vậy phải xác minh trạng thái thực sự đến mapper, không chỉ nhìn tên trạng thái mà indicator đã tạo. [Mã nguồn SimpleStatusAggregator 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.java)

## 4. Khi nào cần một bean HttpCodeStatusMapper?

Bean phù hợp khi chính sách cần viết thành mã, chẳng hạn vừa xử lý một số trạng thái riêng vừa chủ động ủy quyền phần còn lại cho mapper mặc định.

```java
@Bean
HttpCodeStatusMapper applicationHttpCodeStatusMapper() {
    return status -> {
        if ("DEGRADED".equals(status.getCode())
                || Status.UNKNOWN.equals(status)) {
            return 503;
        }
        return HttpCodeStatusMapper.DEFAULT.getStatusCode(status);
    };
}
```

Đây là đoạn khai báo trong một lớp cấu hình Spring; cần import `org.springframework.context.annotation.Bean`. Chính sách của nó là:

- `DEGRADED` và `UNKNOWN` trả `503`.
- `DOWN` và `OUT_OF_SERVICE` được xử lý bằng mapper mặc định nên vẫn trả `503`.
- `UP` cùng trạng thái khác chưa xử lý nhận hành vi dự phòng của mapper mặc định.

So sánh bằng `equals` hoặc so sánh `getCode()`; tránh `status == Status.DOWN` vì có thể nhận một đối tượng `Status` khác mang cùng mã. Đối tượng trạng thái tùy chỉnh được tạo bằng `new Status("DEGRADED")`. Với lambda ở trên, việc so sánh chuỗi Java phân biệt chữ hoa/chữ thường; hãy thống nhất mã mà indicator phát ra.

### 4.1. Bean và properties không tự ghép chính sách

Trong cấu hình tự động chuẩn của Spring Boot 3.3, nhóm health chính chọn một bean `HttpCodeStatusMapper` không gắn qualifier nhóm nếu có. Khi không có bean phù hợp, nó mới tạo `SimpleHttpCodeStatusMapper` từ bảng properties.

Vì vậy một bean như trên **không tự đọc hoặc hợp nhất** `management.endpoint.health.status.http-mapping`. Muốn dùng cả bảng cấu hình và mã bổ sung, bạn phải thiết kế việc kết hợp đó trong bean. Không nên chỉ thêm properties rồi mặc định rằng bean hiện có sẽ dùng chúng.

Giữ một chính sách mapper chính rõ ràng để tránh tình huống có nhiều bean cùng vai trò mà Spring không chọn được. [Cách Spring Boot chọn mapper chính và mapper nhóm](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/AutoConfiguredHealthEndpointGroups.java)

### 4.2. Giữ mapper nhỏ và thuần về ánh xạ

Mapper chỉ cần chuyển một trạng thái thành mã HTTP. Không gọi lại HTTP health từ mapper, không truy vấn cơ sở dữ liệu lần nữa và không ghi trạng thái dùng chung trong mỗi lần ánh xạ. Những công việc đó làm kết quả khó dự đoán hoặc có thể tạo vòng gọi.

Nếu cần biết một phụ thuộc đang hỏng hay không, thông tin ấy nên được thể hiện ở indicator và trạng thái health trước khi đến mapper.

## 5. Thí nghiệm HTTP hoàn chỉnh

Ví dụ sau tạo một ứng dụng độc lập, không yêu cầu có cơ sở dữ liệu hoặc dịch vụ ngoài. Trạng thái được truyền khi khởi động để từng lần thử có kết quả lặp lại được. Trong ứng dụng thật, indicator phải kiểm tra một điều kiện có ý nghĩa thay vì luôn trả trạng thái mô phỏng.

### 5.1. Cấu trúc tệp

```text
health-mapper-demo/
├── pom.xml
├── src/main/java/example/health/HealthMapperApplication.java
├── src/main/resources/application.properties
└── src/main/resources/application-mapping.properties
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>health-mapper-demo</artifactId>
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

`src/main/java/example/health/HealthMapperApplication.java`:

```java
package example.health;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.actuate.health.HttpCodeStatusMapper;
import org.springframework.boot.actuate.health.Status;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;

@SpringBootApplication
public class HealthMapperApplication {
    public static void main(String[] args) {
        SpringApplication.run(HealthMapperApplication.class, args);
    }

    @Bean
    HealthIndicator demoHealthIndicator(
            @Value("${demo.health-status:UP}") String code) {
        Status simulatedStatus = new Status(code);
        return () -> Health.status(simulatedStatus).build();
    }

    @Bean
    @Profile("mapper")
    HttpCodeStatusMapper applicationHttpCodeStatusMapper() {
        return status -> {
            if ("DEGRADED".equals(status.getCode())
                    || Status.UNKNOWN.equals(status)) {
                return 503;
            }
            return HttpCodeStatusMapper.DEFAULT.getStatusCode(status);
        };
    }
}
```

`src/main/resources/application.properties`:

```properties
spring.application.name=health-mapper-demo
management.endpoints.web.exposure.include=health
management.health.defaults.enabled=false
management.endpoint.health.show-details=never
management.endpoint.health.show-components=never
management.endpoint.health.status.order=down,out-of-service,degraded,up,unknown
demo.health-status=UP
```

Trong thí nghiệm, `management.health.defaults.enabled=false` loại các indicator tự cấu hình khỏi phép thử; bean `demoHealthIndicator` do ứng dụng khai báo vẫn tồn tại. Hai cấu hình `show-...=never` giúp chỉ quan sát trạng thái tổng, không đưa chi tiết vào JSON. Chúng không quyết định mã HTTP.

Thứ tự chứa `DEGRADED` đã được khai báo từ đầu để tách riêng ảnh hưởng của mapper. Giữ nguyên chữ hoa của giá trị truyền cho `demo.health-status` như các lệnh bên dưới.

`src/main/resources/application-mapping.properties`:

```properties
management.endpoint.health.status.http-mapping.down=503
management.endpoint.health.status.http-mapping.out-of-service=503
management.endpoint.health.status.http-mapping.degraded=503
```

Hai profile là hai cách chọn chính sách:

| Profile đang dùng | Mapper trong ví dụ |
| --- | --- |
| Không bật profile | Mapper mặc định |
| `mapping` | Bảng properties, giữ hai ánh xạ chuẩn và thêm `DEGRADED` |
| `mapper` | Bean Java, xử lý riêng `DEGRADED`/`UNKNOWN` rồi ủy quyền mặc định |

### 5.2. Đóng gói và khởi động

Tại thư mục chứa `pom.xml`, cần Maven và JDK 21:

```powershell
mvn -q package
java -jar target/health-mapper-demo-1.0.0.jar --demo.health-status=DOWN
```

Chờ ứng dụng khởi động thành công rồi mở terminal khác. Mỗi lần đổi kịch bản, dừng tiến trình bằng `Ctrl+C` trước khi khởi động lệnh mới để không trùng cổng `8080`.

Các lệnh kiểm tra dưới đây dành cho PowerShell trên Windows, gọi `curl.exe` để tránh alias `curl` của một số phiên bản PowerShell. Kiểm tra riêng mã HTTP:

```powershell
curl.exe -sS -o NUL -w "%{http_code}\n" http://localhost:8080/actuator/health
```

Với lần khởi động `DOWN`, stdout:

```text
503
```

Đọc phần thân:

```powershell
curl.exe -sS http://localhost:8080/actuator/health
```

Nội dung JSON:

```json
{"status":"DOWN"}
```

`NUL` là đích bỏ phần thân trên Windows. Khi dùng Bash trên Linux/macOS, lệnh tương ứng để lấy mã là:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' http://localhost:8080/actuator/health
```

Không thêm `--fail` khi mục đích là quan sát cả phản hồi `503` và phần thân; lỗi ở mức HTTP là một kết quả cần kiểm chứng trong thí nghiệm.

### 5.3. So sánh các lần chạy

Mỗi dòng là một lần khởi động riêng, sau đó gọi lại hai lệnh kiểm tra ở trên.

```powershell
java -jar target/health-mapper-demo-1.0.0.jar --demo.health-status=DEGRADED
```

```powershell
java -jar target/health-mapper-demo-1.0.0.jar --spring.profiles.active=mapping --demo.health-status=DEGRADED
```

```powershell
java -jar target/health-mapper-demo-1.0.0.jar --spring.profiles.active=mapping --demo.health-status=DOWN
```

```powershell
java -jar target/health-mapper-demo-1.0.0.jar --spring.profiles.active=mapper --demo.health-status=UNKNOWN
```

| Lần chạy | Trạng thái JSON dự kiến | HTTP dự kiến | Điều cần thấy |
| --- | --- | --- | --- |
| Không profile, `DEGRADED` | `DEGRADED` | `200` | Bộ tổng hợp đã biết trạng thái, mapper mặc định chưa ánh xạ nó |
| `mapping`, `DEGRADED` | `DEGRADED` | `503` | Properties thay cách biểu diễn trạng thái qua HTTP |
| `mapping`, `DOWN` | `DOWN` | `503` | Bảng tùy chỉnh vẫn giữ ánh xạ lỗi chuẩn |
| `mapper`, `UNKNOWN` | `UNKNOWN` | `503` | Bean áp dụng chính sách khác với mặc định `UNKNOWN -> 200` |

Các kết quả HTTP trong bảng giả định gọi trực tiếp ứng dụng ví dụ, không có Spring Security, reverse proxy hoặc cấu hình khác chặn yêu cầu. Không suy ra mã của ứng dụng từ mã mà một proxy tự tạo.

**Thử bẫy cấu hình:** trong dự án thí nghiệm, bỏ hai dòng `down` và `out-of-service` khỏi `application-mapping.properties`, đóng gói lại rồi chạy profile `mapping` với `DOWN`. Phần thân vẫn báo `DOWN` nhưng mã sẽ là `200`. Khôi phục hai dòng đó sau khi quan sát.

## 6. Chạy riêng mapper để kiểm chứng chính xác

Không cần mở web server để kiểm tra một hàm ánh xạ. Chương trình sau đối chiếu bốn mapper với cùng đầu vào, đồng thời chỉ ra sự độc lập của bước tổng hợp.

Lưu thành `experiments/MapperDemo.java`, nằm ngoài `src/main/java` của dự án ở mục 5 để không bổ sung một lớp main khác vào JAR Spring Boot.

```java
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.boot.actuate.health.HttpCodeStatusMapper;
import org.springframework.boot.actuate.health.SimpleHttpCodeStatusMapper;
import org.springframework.boot.actuate.health.SimpleStatusAggregator;
import org.springframework.boot.actuate.health.Status;

public class MapperDemo {
    public static void main(String[] args) {
        Status degraded = new Status("DEGRADED");
        HttpCodeStatusMapper defaults = HttpCodeStatusMapper.DEFAULT;
        HttpCodeStatusMapper partial =
                new SimpleHttpCodeStatusMapper(Map.of("degraded", 503));
        HttpCodeStatusMapper complete = new SimpleHttpCodeStatusMapper(
                Map.of("down", 503, "out-of-service", 503, "degraded", 503));
        HttpCodeStatusMapper policy = status -> {
            if ("DEGRADED".equals(status.getCode())
                    || Status.UNKNOWN.equals(status)) {
                return 503;
            }
            return HttpCodeStatusMapper.DEFAULT.getStatusCode(status);
        };

        for (Status status : List.of(Status.UP, Status.DOWN,
                Status.OUT_OF_SERVICE, Status.UNKNOWN, degraded)) {
            System.out.println(status.getCode()
                    + " | default=" + defaults.getStatusCode(status)
                    + " | partial=" + partial.getStatusCode(status)
                    + " | complete=" + complete.getStatusCode(status)
                    + " | policy=" + policy.getStatusCode(status));
        }

        Set<Status> components = Set.of(Status.UP, degraded);
        System.out.println("aggregate-default="
                + new SimpleStatusAggregator()
                        .getAggregateStatus(components).getCode());
        System.out.println("aggregate-custom="
                + new SimpleStatusAggregator("DOWN", "OUT_OF_SERVICE",
                        "DEGRADED", "UP", "UNKNOWN")
                        .getAggregateStatus(components).getCode());
    }
}
```

Sau khi có thư mục `experiments` và tệp nguồn, chạy tại thư mục chứa `pom.xml`:

```powershell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
$healthDemoClasspath = (Get-Content -Raw -LiteralPath classpath.txt).Trim()
javac --release 21 -encoding UTF-8 -cp $healthDemoClasspath experiments/MapperDemo.java
java -cp "$healthDemoClasspath;experiments" MapperDemo
```

Dấu `;` trong classpath là cú pháp Windows. Nếu chạy trên Linux/macOS, dùng `:` làm dấu phân cách và lấy classpath từ tệp bằng cú pháp của shell tương ứng.

Stdout của `MapperDemo`:

```text
UP | default=200 | partial=200 | complete=200 | policy=200
DOWN | default=503 | partial=200 | complete=503 | policy=503
OUT_OF_SERVICE | default=503 | partial=200 | complete=503 | policy=503
UNKNOWN | default=200 | partial=200 | complete=200 | policy=503
DEGRADED | default=200 | partial=503 | complete=503 | policy=503
aggregate-default=UP
aggregate-custom=DEGRADED
```

Đọc kết quả theo từng thí nghiệm:

1. `default` chứng minh các ánh xạ có sẵn và giá trị dự phòng `200`.
2. `partial` chứng minh bảng chỉ có `degraded` không giữ `DOWN`/`OUT_OF_SERVICE`.
3. `complete` chứng minh khai báo đủ ba mục giữ được hành vi mong muốn.
4. `policy` xử lý `UNKNOWN` riêng nhưng vẫn giữ `DOWN`/`OUT_OF_SERVICE` bằng cách gọi mapper mặc định.
5. Hai dòng `aggregate-...` dùng cùng tập `{UP, DEGRADED}`. Thay thứ tự tổng hợp đổi đầu vào mà mapper sẽ nhận; thay mapper không tự làm việc đó.

Đây là kiểm chứng ở mức API Java; nó không thay thế lần kiểm tra HTTP khi ứng dụng có profile, nhóm health, bộ lọc bảo mật hoặc proxy.

## 7. Phạm vi theo nhóm health

Một ứng dụng có thể có nhiều đối tượng đọc health với yêu cầu khác nhau. Nhóm health cho phép chọn tập indicator và có mapper riêng.

Để thử tiếp trong ứng dụng mục 5, **không bật profile `mapper`**, giữ cấu hình chung rồi thêm các dòng sau vào `application.properties`:

```properties
management.endpoint.health.group.routing.include=demo
management.endpoint.health.group.routing.status.http-mapping.down=503
management.endpoint.health.group.routing.status.http-mapping.out-of-service=503
management.endpoint.health.group.routing.status.http-mapping.degraded=503
```

Khởi động với `--demo.health-status=DEGRADED` và kiểm tra:

```powershell
curl.exe -sS -o NUL -w "%{http_code}\n" http://localhost:8080/actuator/health
curl.exe -sS -o NUL -w "%{http_code}\n" http://localhost:8080/actuator/health/routing
```

Kết quả mã theo thứ tự:

```text
200
503
```

Cả hai đường dẫn nhìn cùng indicator `demo`, nhưng nhóm `routing` sử dụng bảng HTTP riêng. Tên `demo` đến từ bean `demoHealthIndicator` sau khi bỏ hậu tố `HealthIndicator`.

Nếu không cấu hình mapper riêng, nhóm kế thừa mapper chung. Khi có bảng ánh xạ nhóm, đó là bảng riêng của nhóm; đừng giả định nó tự hợp nhất các mục còn thiếu từ bảng chung. Ví dụ đã khai báo đầy đủ `DOWN` và `OUT_OF_SERVICE` cho nhóm.

Có thể khai báo bean gắn `@Qualifier("routing")` để chọn mapper cho nhóm cùng tên. Chỉ định rõ vai trò chung và vai trò nhóm, tránh tạo nhiều bean không phân biệt được. Cách chọn mapper theo qualifier và việc dùng mapper chung làm dự phòng nằm trong [cấu hình HealthEndpointGroups của Spring Boot 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/AutoConfiguredHealthEndpointGroups.java).

Nếu vận dụng cho readiness/liveness, phải xác định đúng ý nghĩa kiểm tra và chính sách của từng nhóm. Đổi mã của health không tự thay đổi ý nghĩa các trạng thái vòng đời ứng dụng; mã được bộ giám sát xem là thành công hay thất bại còn phụ thuộc hợp đồng của bộ giám sát đó.

## 8. Giới hạn và lỗi thường gặp

| Hiện tượng | Điểm cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| JSON `DOWN` nhưng HTTP `200` sau khi thêm trạng thái tùy chỉnh | Bảng tùy chỉnh thiếu `down` | Khai báo lại các trạng thái chuẩn cần giữ |
| Indicator báo `DEGRADED` nhưng JSON tổng là `UP` hoặc `UNKNOWN` | Thứ tự tổng hợp chưa nhận biết trạng thái đó | Kiểm tra `status.order` hoặc `StatusAggregator` |
| Sửa `http-mapping` nhưng HTTP không đổi | Bean Java đang được chọn; hoặc profile cấu hình chưa bật | Xác định mapper thực tế và nguồn cấu hình có hiệu lực |
| Health tổng và nhóm trả mã khác nhau | Hai đường dẫn có thể dùng mapper hoặc tập indicator khác nhau | Kiểm tra cấu hình của đúng nhóm |
| Nhận `401`/`403` hoặc `404` | Bảo mật, khả năng truy cập endpoint, đường dẫn/cổng, quyền xem thành phần | Kiểm tra lớp xử lý yêu cầu trước khi quy cho mapper |
| Nhận `502` từ proxy | Có thể proxy chưa nhận được phản hồi hợp lệ từ ứng dụng | Gọi trực tiếp cổng ứng dụng và đối chiếu log |
| JSON bị ẩn chi tiết nhưng mã HTTP vẫn báo lỗi | `show-details`/`show-components` chỉ điều khiển phần hiển thị | Kiểm tra trạng thái và chính sách mã độc lập |

`HttpCodeStatusMapper` không phải bộ xử lý toàn bộ lỗi HTTP của ứng dụng. Nó không thay mã cho mọi controller, không thiết lập chính sách xác thực và không quy định kết quả JMX vì JMX không có mã HTTP.

Bảng ánh xạ chỉ giải quyết **cách biểu diễn trạng thái đã tính được**. Nếu cơ sở dữ liệu đã phục hồi nhưng indicator vẫn báo `DOWN` vì lỗi trong phép kiểm tra, đổi `DOWN -> 200` chỉ làm mất tín hiệu cho người giám sát.

## 9. Thực hành tự kiểm tra

1. Dùng chương trình `MapperDemo`, thêm `new Status("MAINTENANCE")` vào danh sách đầu vào. Trước khi chạy, dự đoán cả bốn mã. Vì chưa mapper nào xử lý riêng trạng thái đó, cả bốn đều trả `200`.
2. Thêm ánh xạ `maintenance=503` vào một bảng mới. Kiểm tra lại `DOWN` để xác nhận bạn đã chủ động giữ hoặc thay hành vi chuẩn, thay vì vô tình làm mất nó.
3. Trong ứng dụng HTTP, chạy `UNKNOWN` với không profile, profile `mapping` rồi profile `mapper`. Với cấu hình mẫu, mã lần lượt là `200`, `200`, `503`; phần thân vẫn là `UNKNOWN`.
4. Giải thích vì sao `DEGRADED -> 503` không làm tập `{UP, DEGRADED}` tự tổng hợp thành `DEGRADED` khi chưa cấu hình thứ tự.
5. Ghi hợp đồng vận hành cho một trạng thái tùy chỉnh: nó biểu thị điều kiện gì, có cho nhận lưu lượng không, thuộc thứ tự tổng hợp nào, HTTP cần trả gì và hệ thống giám sát sẽ làm gì với mã đó.

Khi kiểm chứng một thay đổi, hãy theo dõi đủ chuỗi **trạng thái thành phần → trạng thái tổng/nhóm → mapper thực tế → mã HTTP nhận được**. Chuỗi này giúp phân biệt lỗi kiểm tra sức khỏe, lỗi tổng hợp và lỗi cấu hình ánh xạ.

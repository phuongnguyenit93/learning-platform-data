# Health endpoint biểu diễn sức khỏe ứng dụng như thế nào

## 1. Từ “tiến trình còn chạy” đến “ứng dụng có khỏe không?”

Một ứng dụng vẫn có thể lắng nghe cổng HTTP trong khi không kết nối được kho dữ liệu, không gửi được thông điệp hoặc đã chủ động ngừng nhận công việc mới. Việc Java chưa thoát không đủ để kết luận ứng dụng phục vụ được nhu cầu của người dùng.

**Health endpoint** của Spring Boot Actuator cung cấp một biểu diễn có cấu trúc về tình trạng ứng dụng, dựa trên các kiểm tra sức khỏe đã được đăng ký. Với đường dẫn mặc định, người gọi gửi:

```http
GET /actuator/health
Accept: application/json
```

Một phản hồi tối giản có thể là:

```json
{"status":"UP"}
```

Cách đọc đúng là: **theo những thành phần được kiểm tra và chính sách tổng hợp hiện tại, trạng thái tổng hợp là UP**.

Không nên diễn giải thành “mọi chức năng nghiệp vụ đều đúng”, “mọi hệ thống bên ngoài đều hoạt động” hoặc “ứng dụng chắc chắn đáp ứng được mọi yêu cầu tiếp theo”. Health chỉ biết những gì các kiểm tra của nó thực sự quan sát.

Bài này đi từ cấu trúc phản hồi đến cách tạo và tổng hợp trạng thái, sau đó dùng một ứng dụng chạy được để kiểm chứng. Ví dụ dùng **Java 21, Spring Boot 3.3.13 và Spring MVC**. Phiên bản được cố định để tái hiện hành vi thuộc dòng 3.3.x; không hàm ý đây là phiên bản mới nhất hay khuyến nghị triển khai sản xuất hiện tại.

## 2. Ba câu hỏi để đọc một phản hồi health

Khi xem health, hãy tách ba câu hỏi:

1. **Đang quan sát những thành phần nào?**
2. **Mỗi thành phần trả trạng thái gì, và chúng được tổng hợp ra sao?**
3. **Phản hồi cho người gọi được hiện những phần nào, với mã HTTP nào?**

Có thể hình dung luồng xử lý:

```text
Yêu cầu GET /actuator/health
    -> Tìm các thành phần sức khỏe đã đăng ký
    -> Lấy kết quả kiểm tra ở các thành phần lá
    -> Tổng hợp trạng thái các nhánh và toàn cây
    -> Áp dụng chính sách hiển thị thành phần/chi tiết
    -> Ánh xạ trạng thái sức khỏe sang mã HTTP
    -> Trả phản hồi JSON
```

Đây là mô hình giải thích các trách nhiệm chính, không phải cam kết rằng mọi kiểm tra chạy đồng thời hay mọi thành phần được đo đúng cùng một thời điểm.

## 3. status, components và details có vai trò khác nhau

Với phản hồi dạng V3 của Actuator, các trường quan trọng là:

| Trường | Vai trò khi đọc |
| --- | --- |
| `status` ở gốc | Trạng thái tổng hợp cho phạm vi đang được hỏi |
| `components` | Các thành phần con nếu được phép hiển thị |
| `components.<tên>.status` | Trạng thái của một thành phần |
| `components.<tên>.components` | Các thành phần lồng trong một nhánh |
| `details` | Dữ liệu giải thích do một thành phần cung cấp, nếu được phép hiển thị |

Health có thể biểu diễn một cây lồng nhau, không chỉ một danh sách phẳng. API còn cho phép hỏi một thành phần hoặc một thành phần con qua đường dẫn tương ứng. [Cấu trúc phản hồi Health của Actuator 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

Điểm cần lưu ý:

- `components` mô tả cấu trúc.
- `details` cung cấp thông tin bổ sung.
- `status` là dữ liệu đầu vào cho quyết định tổng hợp.

Spring Boot không tự suy ra trạng thái bằng cách đọc ý nghĩa câu chữ trong `details`. Chẳng hạn, đoạn minh họa API sau vẫn tạo trạng thái UP:

```java
Health.up()
        .withDetail("queueAvailable", false)
        .build();
```

Đây là biểu thức minh họa bên trong mã dùng API `Health`, không phải một chương trình Java độc lập. Nếu điều kiện kiểm tra thất bại, người viết kiểm tra phải trả trạng thái phù hợp, thay vì chỉ ghi một chi tiết mang ý nghĩa lỗi.

Không có `components` hoặc `details` trong JSON cũng chưa chứng minh ứng dụng không có kiểm tra con. Những trường này có thể đã bị chính sách hiển thị ẩn đi.

## 4. Ai tạo ra thông tin sức khỏe?

### 4.1. HealthIndicator tạo kết quả ở một thành phần lá

`HealthIndicator` là giao diện cho một kiểm tra sức khỏe trong mô hình Servlet dùng ở bài. Phương thức `health()` trả về `Health`, gồm trạng thái và có thể có các chi tiết giải thích. Giao diện này cũng là một giao diện hàm (functional interface) nên có thể triển khai bằng lambda. [API HealthIndicator 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthIndicator.html).

Một kiểm tra thật có thể xác minh điều kiện cần cho việc phục vụ, chẳng hạn khả năng lấy kết nối cơ sở dữ liệu hoặc dung lượng đĩa còn trên ngưỡng đã chọn.

Chất lượng tín hiệu phụ thuộc vào điều kiện kiểm tra:

- Chỉ xác minh một đối tượng cấu hình tồn tại không chứng minh dịch vụ từ xa còn dùng được.
- Một thao tác kết nối thành công không chứng minh mọi truy vấn nghiệp vụ đều đúng.
- Kiểm tra quá rộng, quá chậm hoặc gây thay đổi dữ liệu có thể tạo thêm vấn đề khi hệ thống đang gặp sự cố.

Health là kết quả của một phép kiểm tra có phạm vi, không phải một lời bảo đảm tổng quát.

### 4.2. HealthContributor biểu diễn thành phần lá hoặc nhánh

`HealthContributor` là khái niệm bao quát:

- Một `HealthIndicator` cung cấp kết quả tại một lá.
- Một `CompositeHealthContributor` gom nhiều thành phần con thành một nhánh.

`CompositeHealthContributor.fromMap(...)` có thể tạo một nhánh từ bản đồ tên thành phần sang contributor. [API CompositeHealthContributor 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/CompositeHealthContributor.html).

Nhờ vậy, có thể mô hình hóa:

```text
Sức khỏe toàn ứng dụng
├── heartbeat
└── orderFlow
    ├── storage
    └── queue
```

Trong cây này, `orderFlow` có trạng thái tổng hợp từ hai con của nó. Trạng thái gốc tiếp tục tổng hợp từ `heartbeat` và `orderFlow`.

Danh sách thành phần thực tế phụ thuộc những contributor đã được đăng ký. Spring Boot có các kiểm tra tự cấu hình khi đáp ứng điều kiện thư viện/cấu hình phù hợp; không tự phát hiện đầy đủ mọi phụ thuộc nghiệp vụ chỉ từ mã nguồn của ứng dụng.

## 5. Ý nghĩa các trạng thái và cách tổng hợp

### 5.1. Các trạng thái thông dụng

| Trạng thái | Cách hiểu ở mức nền tảng |
| --- | --- |
| `UP` | Thành phần đáp ứng điều kiện sức khỏe mà phép kiểm tra xác định |
| `DOWN` | Phép kiểm tra xác định thành phần đang có vấn đề |
| `OUT_OF_SERVICE` | Thành phần đang được coi là ngoài khả năng phục vụ |
| `UNKNOWN` | Chưa xác định được trạng thái theo kết quả hoặc chính sách hiện tại |

Ứng dụng quyết định điều kiện nào dẫn tới từng trạng thái. Framework không tự biết một đợt bảo trì có phải là OUT_OF_SERVICE hay không nếu không có thành phần cung cấp thông tin đó.

`Health.up()`, `Health.down()`, `Health.outOfService()`, `Health.unknown()` và `Health.status(...)` là các cách tạo kết quả bằng API. [API Health 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/Health.html).

### 5.2. Tổng hợp theo mức ưu tiên, không theo biểu quyết

Với `SimpleStatusAggregator` mặc định của Spring Boot 3.3.13, thứ tự ưu tiên là:

```text
DOWN -> OUT_OF_SERVICE -> UP -> UNKNOWN
```

Trong các trạng thái được nhận diện, trạng thái xuất hiện sớm nhất trong danh sách quyết định kết quả tổng hợp. [Mã nguồn SimpleStatusAggregator 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.java).

Ví dụ:

| Các trạng thái con | Kết quả theo mặc định |
| --- | --- |
| UP, UP | UP |
| DOWN, UP, UP | DOWN |
| OUT_OF_SERVICE, UP | OUT_OF_SERVICE |
| DOWN, OUT_OF_SERVICE | DOWN |
| UNKNOWN, UP | UP |
| UNKNOWN | UNKNOWN |

Một thành phần DOWN không bị “đánh bại” bởi nhiều thành phần UP. Đây không phải tỷ lệ số phiếu, điểm trung bình hoặc thứ tự khai báo bean.

Trường hợp **UNKNOWN cùng UP cho ra UP** đặc biệt đáng chú ý. UNKNOWN không mặc nhiên là mức nghiêm trọng hơn UP trong chính sách mặc định này. Vì vậy, chỉ nhìn UP ở gốc chưa đủ để kết luận mọi lá đều có kết quả UP.

Nếu cần một chính sách khác, có thể cấu hình thứ tự hoặc thay bộ tổng hợp. Khi đó phải đọc phản hồi theo chính sách mới, không tiếp tục áp dụng bảng mặc định một cách máy móc.

### 5.3. Trạng thái tùy chỉnh cần một chính sách tương ứng

Một contributor có thể tạo mã riêng như `DEGRADED`, nhưng một cái tên có vẻ nghiêm trọng không tự làm nó đứng trước UP.

Nếu bộ tổng hợp mặc định chưa nhận diện mã đó, nó không trở thành mức ưu tiên mới chỉ vì xuất hiện trong kết quả. Khi không có trạng thái nào thuộc danh sách được nhận diện, kết quả tổng hợp là UNKNOWN.

Thêm một mã sức khỏe mới vì vậy cần xem xét cả chính sách tổng hợp và ánh xạ HTTP. Hai việc này có trách nhiệm khác nhau.

## 6. Trạng thái sức khỏe khác mã HTTP

Đối tượng sức khỏe không tự chứa một mã HTTP bắt buộc. Khi truy cập qua web, `HttpCodeStatusMapper` ánh xạ trạng thái sức khỏe sang mã phản hồi; `SimpleHttpCodeStatusMapper` cung cấp cách ánh xạ mặc định. [API ánh xạ trạng thái sang HTTP](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleHttpCodeStatusMapper.html).

Với cấu hình mặc định của Spring Boot 3.3:

| Trạng thái của phạm vi được hỏi | Mã HTTP |
| --- | --- |
| DOWN | 503 |
| OUT_OF_SERVICE | 503 |
| UP | 200 |
| UNKNOWN | 200 |
| Mã khác chưa có ánh xạ riêng | 200 |

Do đó:

- HTTP 503 kèm JSON `{"status":"DOWN"}` có thể là một kết quả health được trả chủ động; không đồng nghĩa bộ xử lý HTTP đã bị sập.
- HTTP 200 có thể đi cùng UNKNOWN, không chỉ UP.
- Không có phản hồi hoặc không kết nối được là một tình huống khác với việc nhận được phản hồi health báo DOWN.

Một hệ thống giám sát phải biết mình đang đánh giá mã HTTP, nội dung trạng thái hay cả hai. Không suy ra toàn bộ chính sách sức khỏe từ riêng một con số HTTP.

Việc tùy chỉnh ánh xạ HTTP có thể thay đổi bảng này. Khi thêm ánh xạ trong cấu hình Spring Boot 3.3, cần khai báo lại các ánh xạ DOWN và OUT_OF_SERVICE nếu muốn giữ chúng; không giả định chúng luôn được giữ bên cạnh cấu hình tùy chỉnh.

## 7. Mức hiển thị không làm thay đổi kết quả kiểm tra

Hai thuộc tính liên quan:

```properties
management.endpoint.health.show-components=never
management.endpoint.health.show-details=never
```

- `show-components` kiểm soát việc hiện cây thành phần.
- `show-details` kiểm soát việc hiện dữ liệu giải thích.
- Các lựa chọn gồm `never`, `when-authorized` và `always`.

Trong cấu hình mặc định, phản hồi thường chỉ thể hiện trạng thái tổng hợp. Có thể cho người được phép xem thêm thông tin, nhưng đó là quyết định hiển thị dữ liệu, không phải quyết định một phụ thuộc có khỏe hay không. [Cấu hình thông tin health của Actuator 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health).

Ví dụ, nếu một thành phần vẫn DOWN, ẩn nó khỏi JSON không biến trạng thái gốc thành UP. Phản hồi có thể chỉ còn:

```json
{"status":"DOWN"}
```

Mã HTTP mặc định vẫn là 503.

Chi tiết có thể chứa đường dẫn, tên tài nguyên, thông tin lỗi hoặc cấu trúc nội bộ. Vì vậy, chỉ bật hiển thị chi tiết theo nhu cầu và quyền truy cập phù hợp. Chính sách hiển thị không thay thế bảo vệ endpoint ở lớp mạng và xác thực/phân quyền.

## 8. Dự án thực hành: nhìn thấy cây và trạng thái thay đổi

Ví dụ sau mô phỏng cây gồm hai thành phần ở gốc là `heartbeat` và `orderFlow`; nhánh `orderFlow` chứa `storage` và `queue`. Mọi kiểm tra đều là **mô phỏng trong bộ nhớ**, không xác minh một cơ sở dữ liệu hay hàng đợi thật.

Ta thay trạng thái `storage` bằng thuộc tính `demo.storage-status` để quan sát biểu diễn và chính sách tổng hợp. Không thêm endpoint thay đổi trạng thái và không giả vờ rằng một dependency thật đã được kiểm tra.

Cấu trúc dự án:

```text
health-representation-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/healthview/
    │   │   ├── HealthViewApplication.java
    │   │   └── DemoHealthConfiguration.java
    │   └── resources/application.yml
    └── test/java/com/example/healthview/
        └── HealthEndpointRepresentationTest.java
```

Dùng Maven với JDK 21; lần dựng đầu cần tải thư viện từ kho Maven. Đây là dự án Spring Boot, không phải các tệp có thể chạy riêng bằng `javac TenLop.java`.

### 8.1. pom.xml

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
    <artifactId>health-representation-lab</artifactId>
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

### 8.2. src/main/resources/application.yml

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
  storage-status: UP
```

Hai lựa chọn dành riêng cho bài thực hành:

- `show-components=always` và `show-details=always` giúp quan sát đầy đủ cây cùng dữ liệu mô phỏng.
- `management.health.defaults.enabled=false` bỏ các kiểm tra tự cấu hình mặc định để cây ví dụ không thay đổi theo môi trường máy chạy. Các contributor do ta tự khai báo vẫn được sử dụng.

Không sao chép việc tắt kiểm tra mặc định sang ứng dụng thật mà chưa đánh giá nhu cầu. Trong môi trường thật, những kiểm tra đó có thể cung cấp tín hiệu cần thiết.

Ứng dụng chỉ lắng nghe trên địa chỉ vòng lặp `127.0.0.1` và chỉ đưa health ra HTTP. Dự án không thêm Spring Security; việc cho xem chi tiết công khai trong ví dụ chỉ nhằm quan sát dữ liệu mô phỏng trên máy cá nhân.

### 8.3. HealthViewApplication.java

Đặt tại `src/main/java/com/example/healthview/HealthViewApplication.java`.

```java
package com.example.healthview;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HealthViewApplication {
    public static void main(String[] args) {
        SpringApplication.run(HealthViewApplication.class, args);
    }
}
```

### 8.4. DemoHealthConfiguration.java

Đặt tại `src/main/java/com/example/healthview/DemoHealthConfiguration.java`.

```java
package com.example.healthview;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.health.CompositeHealthContributor;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthContributor;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class DemoHealthConfiguration {
    @Bean
    HealthIndicator heartbeatHealthIndicator() {
        return () -> Health.up()
                .withDetail("check", "simulated")
                .build();
    }

    @Bean(name = "orderFlow")
    CompositeHealthContributor orderFlow(
            @Value("${demo.storage-status}") String storageStatus) {
        HealthIndicator storage = () -> Health.status(storageStatus)
                .withDetail("check", "simulated")
                .build();
        HealthIndicator queue = () -> Health.up()
                .withDetail("check", "simulated")
                .build();

        Map<String, HealthContributor> children = new LinkedHashMap<>();
        children.put("storage", storage);
        children.put("queue", queue);
        return CompositeHealthContributor.fromMap(children);
    }
}
```

Cách đối chiếu mã với phản hồi:

| Trong mã | Trong cây health |
| --- | --- |
| Bean `heartbeatHealthIndicator` | Thành phần `heartbeat` |
| Bean được đặt tên rõ là `orderFlow` | Nhánh `orderFlow` |
| Khóa `storage` trong bản đồ con | Thành phần `orderFlow/storage` |
| Khóa `queue` trong bản đồ con | Thành phần `orderFlow/queue` |
| `withDetail("check", "simulated")` | Dữ liệu `details.check` ở lá |

Tên của một HealthIndicator được suy ra từ tên bean, bỏ hậu tố `HealthIndicator` nếu có. Trong ví dụ, bean `heartbeatHealthIndicator` vì thế xuất hiện dưới tên `heartbeat`.

Các hàm ở đây chỉ trả kết quả mô phỏng. Đặc biệt, tên `storage` không làm Spring tự kết nối một nơi lưu trữ thật. Muốn kiểm tra phụ thuộc thật, người viết indicator phải chọn và thực hiện phép kiểm tra phù hợp.

## 9. Quan sát kết quả và giải thích nguyên nhân

### 9.1. Tất cả thành phần mô phỏng đều UP

Tại thư mục chứa `pom.xml`, mở PowerShell với `JAVA_HOME` trỏ đến JDK 21:

```powershell
mvn spring-boot:run
```

Từ terminal thứ hai:

```powershell
curl.exe -s -i -H "Accept: application/json" http://127.0.0.1:8080/actuator/health
```

Mã HTTP là 200. Phần JSON có nội dung tương đương dưới đây; thứ tự trường và cách xuống dòng không phải hợp đồng cần dựa vào:

```json
{
  "status": "UP",
  "components": {
    "heartbeat": {
      "status": "UP",
      "details": {
        "check": "simulated"
      }
    },
    "orderFlow": {
      "status": "UP",
      "components": {
        "storage": {
          "status": "UP",
          "details": {
            "check": "simulated"
          }
        },
        "queue": {
          "status": "UP",
          "details": {
            "check": "simulated"
          }
        }
      }
    }
  }
}
```

Đọc từ dưới lên:

1. `storage` và `queue` đều UP nên `orderFlow` là UP.
2. `orderFlow` và `heartbeat` đều UP nên gốc là UP.
3. Trạng thái gốc UP được ánh xạ sang HTTP 200.

Không dùng riêng trường `details.check` để đánh giá trạng thái. Nó chỉ nhắc rằng dữ liệu đang được mô phỏng.

### 9.2. Một lá DOWN kéo nhánh và gốc xuống DOWN

Dừng ứng dụng bằng Ctrl+C, rồi chạy lại:

```powershell
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.storage-status=DOWN"
```

Gọi lại health. Những phần thay đổi là:

```text
components.orderFlow.components.storage.status = DOWN
components.orderFlow.status = DOWN
status = DOWN
HTTP = 503
```

`heartbeat` và `queue` vẫn UP, nhưng không làm mất trạng thái DOWN của `storage`.

HTTP 503 ở đây chứng minh ứng dụng vẫn xử lý được yêu cầu health và đang báo một trạng thái không khỏe. Nó không đồng nghĩa JVM đã ngừng chạy.

### 9.3. Hỏi một nhánh hoặc một lá

Trong phiên chạy có `storage=DOWN`:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health/heartbeat
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health/orderFlow
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/health/orderFlow/storage
```

Kết quả theo thứ tự:

```text
503
200
503
503
```

Các đường dẫn hỏi các phạm vi khác nhau, nên mã HTTP có thể khác nhau trong cùng một thời điểm.

Xem riêng lá:

```powershell
curl.exe -s -H "Accept: application/json" http://127.0.0.1:8080/actuator/health/orderFlow/storage
```

Nội dung JSON tương đương:

```json
{
  "status": "DOWN",
  "details": {
    "check": "simulated"
  }
}
```

Đây là kết quả của lá đang được hỏi, không phải toàn bộ cây được bọc lại. Đường dẫn thành phần chỉ hoạt động khi contributor tồn tại và chính sách hiển thị/truy cập cho phép; không nên giả định ai cũng được xem mọi đường dẫn con.

Với cấu hình cục bộ hiện tại, `/actuator/health/notRegistered` trả 404 vì không có contributor đó. Đây là tình huống khác với một contributor có trạng thái UNKNOWN.

### 9.4. UNKNOWN ở lá không nhất thiết làm gốc thành UNKNOWN

Dừng và chạy lại ứng dụng:

```powershell
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.storage-status=UNKNOWN"
```

Dự đoán và đối chiếu:

| Phạm vi | Trạng thái | HTTP mặc định |
| --- | --- | --- |
| `storage` | UNKNOWN | 200 |
| `orderFlow`, gồm storage UNKNOWN và queue UP | UP | 200 |
| Gốc, gồm heartbeat UP và orderFlow UP | UP | 200 |

Nếu một điều kiện quan trọng không thể kiểm tra được, người thiết kế phải cân nhắc trạng thái và chính sách phù hợp. Không chọn UNKNOWN chỉ vì thấy từ này có vẻ “an toàn hơn DOWN”, rồi kỳ vọng nó tự chặn lưu lượng.

### 9.5. Ẩn cây chỉ thay đổi biểu diễn

Dừng và chạy lại:

```powershell
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.storage-status=DOWN --management.endpoint.health.show-components=never --management.endpoint.health.show-details=never"
```

Gọi health gốc vẫn nhận HTTP 503, nhưng JSON chỉ còn:

```json
{"status":"DOWN"}
```

Nếu chỉ muốn hiện cấu trúc mà không hiện chi tiết, giữ `show-components=always` và đặt `show-details=never`. Khi đó các trạng thái con vẫn hiện, còn `details.check` không được trả ra.

Mỗi lệnh khởi động trong các mục trên thay thế phiên chạy trước; không chạy đồng thời nhiều ứng dụng trên cổng 8080.

## 10. Kiểm thử để xác nhận cách biểu diễn

Đặt tệp sau tại `src/test/java/com/example/healthview/HealthEndpointRepresentationTest.java`.

Kiểm thử tạo ngữ cảnh Spring cho từng cấu hình và dùng MockMvc để gọi lớp xử lý HTTP trong ứng dụng. Không cần mở cổng mạng thật. Bộ kiểm thử kiểm tra cả cấu trúc JSON, tổng hợp trạng thái, mã HTTP, cách ẩn thông tin và trường hợp thiếu contributor.

```java
package com.example.healthview;

import java.util.Set;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.boot.actuate.health.SimpleHttpCodeStatusMapper;
import org.springframework.boot.actuate.health.SimpleStatusAggregator;
import org.springframework.boot.actuate.health.Status;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

class HealthEndpointRepresentationTest {
    private final ObjectMapper json = new ObjectMapper();

    private WebApplicationContextRunner application(String... properties) {
        return new WebApplicationContextRunner()
                .withInitializer(new ConfigDataApplicationContextInitializer())
                .withUserConfiguration(HealthViewApplication.class)
                .withPropertyValues(properties);
    }

    @ParameterizedTest
    @CsvSource({
            "UP, UP, 200",
            "DOWN, DOWN, 503",
            "OUT_OF_SERVICE, OUT_OF_SERVICE, 503",
            "UNKNOWN, UP, 200"
    })
    void treeAndHttpStatusFollowAggregation(
            String storageStatus, String overallStatus, int httpStatus) {
        application("demo.storage-status=" + storageStatus).run(context -> {
            MockMvc mvc = MockMvcBuilders
                    .webAppContextSetup(context.getSourceApplicationContext())
                    .build();

            var root = mvc.perform(get("/actuator/health"))
                    .andReturn().getResponse();
            assertThat(root.getStatus()).isEqualTo(httpStatus);
            JsonNode body = json.readTree(root.getContentAsString());
            assertThat(body.path("status").asText()).isEqualTo(overallStatus);
            assertThat(body.path("components").size()).isEqualTo(2);
            assertThat(body.at("/components/heartbeat/status").asText())
                    .isEqualTo("UP");
            assertThat(body.at("/components/orderFlow/status").asText())
                    .isEqualTo(overallStatus);
            assertThat(body.at("/components/orderFlow/components/storage/status")
                    .asText()).isEqualTo(storageStatus);
            assertThat(body.at("/components/orderFlow/components/queue/status")
                    .asText()).isEqualTo("UP");

            var leaf = mvc.perform(get("/actuator/health/orderFlow/storage"))
                    .andReturn().getResponse();
            assertThat(leaf.getStatus()).isEqualTo(
                    new SimpleHttpCodeStatusMapper()
                            .getStatusCode(new Status(storageStatus)));
            assertThat(json.readTree(leaf.getContentAsString())
                    .path("status").asText()).isEqualTo(storageStatus);
        });
    }

    @Test
    void hidingRepresentationDoesNotTurnDownIntoUp() {
        application(
                "demo.storage-status=DOWN",
                "management.endpoint.health.show-components=never",
                "management.endpoint.health.show-details=never").run(context -> {
            MockMvc mvc = MockMvcBuilders
                    .webAppContextSetup(context.getSourceApplicationContext())
                    .build();
            var response = mvc.perform(get("/actuator/health"))
                    .andReturn().getResponse();
            assertThat(response.getStatus()).isEqualTo(503);
            JsonNode body = json.readTree(response.getContentAsString());
            assertThat(body.size()).isEqualTo(1);
            assertThat(body.path("status").asText()).isEqualTo("DOWN");
        });
    }

    @Test
    void componentTreeCanBeVisibleWithoutDetails() {
        application("management.endpoint.health.show-details=never")
                .run(context -> {
                    MockMvc mvc = MockMvcBuilders
                            .webAppContextSetup(context.getSourceApplicationContext())
                            .build();
                    var response = mvc.perform(get("/actuator/health"))
                            .andReturn().getResponse();
                    assertThat(response.getStatus()).isEqualTo(200);
                    JsonNode body = json.readTree(response.getContentAsString());
                    assertThat(body.has("components")).isTrue();
                    assertThat(body.at("/components/heartbeat")
                            .has("details")).isFalse();
                    assertThat(body.at("/components/orderFlow/components/storage")
                            .has("details")).isFalse();
                });
    }

    @Test
    void missingContributorIsNotUnknownHealth() {
        application().run(context -> {
            MockMvc mvc = MockMvcBuilders
                    .webAppContextSetup(context.getSourceApplicationContext())
                    .build();
            assertThat(mvc.perform(get("/actuator/health/notRegistered"))
                    .andReturn().getResponse().getStatus()).isEqualTo(404);
        });
    }

    @Test
    void aggregatorHasKnownOrderAndUnknownFallback() {
        var aggregator = new SimpleStatusAggregator();
        assertThat(aggregator.getAggregateStatus(Set.of(Status.UP, Status.UNKNOWN)))
                .isEqualTo(Status.UP);
        assertThat(aggregator.getAggregateStatus(Set.of(Status.UNKNOWN)))
                .isEqualTo(Status.UNKNOWN);
        assertThat(aggregator.getAggregateStatus(Set.of(
                Status.UP, new Status("DEGRADED")))).isEqualTo(Status.UP);
    }

    @Test
    void healthStatusIsMappedSeparatelyToHttp() {
        var mapper = new SimpleHttpCodeStatusMapper();
        assertThat(mapper.getStatusCode(Status.DOWN)).isEqualTo(503);
        assertThat(mapper.getStatusCode(Status.OUT_OF_SERVICE)).isEqualTo(503);
        assertThat(mapper.getStatusCode(Status.UP)).isEqualTo(200);
        assertThat(mapper.getStatusCode(Status.UNKNOWN)).isEqualTo(200);
        assertThat(mapper.getStatusCode(new Status("DEGRADED"))).isEqualTo(200);
    }
}
```

Tại thư mục chứa `pom.xml`:

```powershell
mvn test
```

Phần kết quả thành công cần thấy:

```text
Tests run: 9, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Bốn bộ tham số của kiểm thử đầu cộng với năm kiểm thử còn lại tạo thành chín ca. Log khởi tạo và thời gian chạy có thể khác nhau.

Những kết luận được kiểm chứng:

- DOWN và OUT_OF_SERVICE ở lá ảnh hưởng nhánh và gốc theo thứ tự mặc định.
- UNKNOWN ở một lá có thể cùng tồn tại với UP ở gốc.
- Trạng thái của lá và trạng thái của gốc là hai phạm vi khác nhau.
- Ẩn cây và chi tiết không đổi DOWN thành UP.
- Có thể hiện trạng thái các thành phần mà không hiện dữ liệu chi tiết.
- Không có contributor tại đường dẫn không giống một contributor báo UNKNOWN.
- Tổng hợp trạng thái và ánh xạ HTTP là hai cơ chế riêng.
- Mã tùy chỉnh chưa được đưa vào chính sách không tự có mức ưu tiên hay mã HTTP lỗi.

Kiểm thử MockMvc không chứng minh cổng, tuyến mạng, TLS hoặc công cụ giám sát bên ngoài đã được cấu hình đúng. Nó chứng minh hành vi biểu diễn bên trong ứng dụng theo các điều kiện đã nêu.

## 11. Health trả lời được gì trong vận hành?

### 11.1. Một kết quả có phạm vi và thời điểm

Một phản hồi health phản ánh kết quả những kiểm tra được lấy cho yêu cầu đó. Các thành phần có thể được kiểm tra lần lượt; phụ thuộc cũng có thể đổi trạng thái ngay sau khi được kiểm tra.

Vì vậy, không coi toàn cây là ảnh chụp giao dịch nguyên tử của mọi hệ thống. Mức độ cập nhật còn phụ thuộc cách viết phép kiểm tra và việc lưu đệm kết quả nếu có cấu hình.

Health endpoint cũng không tự trở thành kho lịch sử. Nếu muốn biết một phụ thuộc đã DOWN bao lâu hoặc mức độ chập chờn, cần cơ chế quan sát theo thời gian phù hợp.

### 11.2. Tín hiệu health không thay thế các tín hiệu khác

| Câu hỏi vận hành | Tín hiệu cần dùng |
| --- | --- |
| Các điều kiện sức khỏe đã chọn hiện có đáp ứng không? | Health |
| Độ trễ, lưu lượng hoặc tỷ lệ lỗi thay đổi thế nào theo thời gian? | Số liệu giám sát |
| Sự kiện hoặc lỗi nào đã xảy ra? | Log, dấu vết thực thi phù hợp |
| Một quy trình nghiệp vụ cụ thể có thực hiện đúng từ đầu đến cuối không? | Kiểm thử hoặc kiểm tra tổng hợp phù hợp với quy trình |

Một health UP không phủ nhận việc tỷ lệ lỗi nghiệp vụ đang tăng. Ngược lại, DOWN ở một phụ thuộc cần được đọc theo phạm vi phép kiểm tra để quyết định cách phản ứng.

Đặc biệt, không đồng nhất câu hỏi “tiến trình có cần khởi động lại không?” với câu hỏi “mọi phụ thuộc hiện có dùng được không?”. Một phụ thuộc từ xa gặp lỗi không mặc nhiên được sửa bằng cách khởi động lại toàn bộ ứng dụng.

### 11.3. Thêm kiểm tra theo nhu cầu có ý nghĩa

Trước khi thêm một indicator thật, cần trả lời:

1. Điều kiện nào đang được kiểm tra?
2. Điều kiện đó liên quan thế nào đến khả năng phục vụ?
3. Phép kiểm tra có giới hạn thời gian và chi phí phù hợp không?
4. Nếu điều kiện không xác định được, nên trả trạng thái nào?
5. Trạng thái đó sẽ được tổng hợp và ánh xạ HTTP ra sao?
6. Chi tiết nào cần cho chẩn đoán, và ai được xem?

Không thêm một kiểm tra luôn UP chỉ để làm cây có nhiều thành phần. Kiểm tra mô phỏng trong bài chỉ giúp hiểu cơ chế; một kiểm tra vận hành cần mang lại tín hiệu thực tế.

## 12. Lỗi đọc và thiết kế thường gặp

| Cách hiểu hoặc lựa chọn sai | Điều cần sửa |
| --- | --- |
| Thấy cổng HTTP mở nên coi mọi chức năng đều khỏe | Phân biệt tiến trình đang chạy với những điều kiện phục vụ thực sự được kiểm tra |
| Thấy UP ở gốc nên cho rằng mọi lá đều UP | Xem phạm vi contributor và chính sách tổng hợp, đặc biệt với UNKNOWN |
| Cho rằng nhiều UP sẽ làm mất một DOWN | Tổng hợp mặc định dùng mức ưu tiên, không biểu quyết |
| Cho rằng UNKNOWN luôn nghiêm trọng hơn UP | Kiểm tra thứ tự thực tế; mặc định 3.3.13 đặt UP trước UNKNOWN |
| Thêm DEGRADED rồi chờ nó tự làm HTTP thành 503 | Thiết kế cả tổng hợp và ánh xạ HTTP cho mã mới |
| Đặt một chuỗi lỗi trong details nhưng vẫn trả UP | Trạng thái phải phản ánh điều kiện kiểm tra; framework không đọc nghĩa câu chữ để suy ra lỗi |
| Coi thiếu components là không có contributor | Có thể cây đã bị ẩn bởi chính sách hiển thị |
| Ẩn một thành phần rồi tưởng nó không tham gia tổng hợp | Hiển thị dữ liệu và tính trạng thái là các trách nhiệm khác nhau |
| Coi HTTP 503 của health là bằng chứng JVM đã chết | Ứng dụng có thể đang chủ động trả kết quả DOWN hoặc OUT_OF_SERVICE |
| Coi mọi HTTP 200 là trạng thái UP | UNKNOWN và mã chưa ánh xạ riêng cũng có thể là 200 |
| Coi 404 ở đường dẫn con là trạng thái UNKNOWN | Phân biệt không có tài nguyên contributor với tài nguyên có kết quả chưa xác định |
| Dùng kiểm tra tốn nhiều thời gian hoặc làm thay đổi nghiệp vụ | Chọn phép kiểm tra có chi phí phù hợp và tránh tạo tác dụng phụ |
| Cho hiện toàn bộ details để tiện chẩn đoán | Giới hạn thông tin theo nhu cầu và quyền truy cập |
| Tắt các kiểm tra mặc định vì ví dụ đã tắt | Cấu hình của bài dùng để tạo cây xác định; ứng dụng thật cần đánh giá từng tín hiệu |

## 13. Tự kiểm tra mô hình đã hiểu

Với thứ tự mặc định:

```text
Ứng dụng
├── A: UP
└── B
    ├── B1: OUT_OF_SERVICE
    └── B2: UNKNOWN
```

Hãy dự đoán trước khi xem đáp án:

1. Trạng thái của B là gì?
2. Trạng thái gốc là gì?
3. HTTP khi hỏi gốc là bao nhiêu?
4. Nếu ẩn components và details, trạng thái gốc có đổi không?
5. Nếu hỏi riêng B2, trạng thái và mã HTTP mặc định là gì?

Đáp án:

| Câu hỏi | Kết quả | Lý do |
| --- | --- | --- |
| Trạng thái B | OUT_OF_SERVICE | OUT_OF_SERVICE đứng trước UNKNOWN |
| Trạng thái gốc | OUT_OF_SERVICE | OUT_OF_SERVICE đứng trước UP |
| HTTP của gốc | 503 | Ánh xạ mặc định cho OUT_OF_SERVICE |
| Khi ẩn cây/chi tiết | Vẫn OUT_OF_SERVICE và HTTP 503 | Chỉ thay đổi biểu diễn |
| Hỏi riêng B2 | UNKNOWN, HTTP 200 | Phạm vi là lá B2 và dùng ánh xạ mặc định |

Sau đó đổi B1 thành UP. Khi ấy B tổng hợp thành UP, rồi gốc cũng UP, dù B2 vẫn UNKNOWN.

Người học cần giải thích được từng kết quả bằng ba lớp: contributor cung cấp trạng thái, bộ tổng hợp quyết định trạng thái của phạm vi được hỏi, và lớp web quyết định biểu diễn cùng mã HTTP. Đó là cơ sở để đọc health có căn cứ trước khi thiết kế những chính sách kiểm tra phức tạp hơn.

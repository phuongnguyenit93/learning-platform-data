# Cấu trúc status, components và details trong phản hồi health

## 1. Đọc health như một cây kết quả kiểm tra

Phản hồi health không chỉ là một cờ “ứng dụng còn sống”. Nó có thể biểu diễn một cây: toàn hệ thống ở gốc, các bộ phận ở những nhánh và kết quả kiểm tra cụ thể ở lá.

Ba trường cần phân biệt:

| Trường | Câu hỏi nó trả lời |
| --- | --- |
| `status` | Nút đang xét có trạng thái sức khỏe nào? |
| `components` | Nút này được cấu thành từ những nút con nào? |
| `details` | Có thông tin bổ sung nào giải thích kết quả của nút này? |

Ví dụ ngắn:

~~~json
{
  "status": "UP",
  "components": {
    "inventory": {
      "status": "UP",
      "details": {
        "availableItems": 12
      }
    }
  }
}
~~~

Đọc từ ngoài vào trong:

1. Trạng thái tổng thể là `UP`.
2. Có một thành phần tên `inventory`.
3. Thành phần đó cũng `UP`.
4. Số `12` là dữ liệu bổ sung do phép kiểm tra cung cấp, không phải mã trạng thái hay điểm sức khỏe.

Bài dùng **Spring Boot 3.3.x, Java 21, Servlet/Spring MVC và định dạng Actuator API V3**. Các JSON là ví dụ có chủ đích; ứng dụng khác có thể có thêm hoặc bớt thành phần. Cấu trúc V3 được mô tả trong [API health 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

## 2. status luôn thuộc về một phạm vi cụ thể

### 2.1. Trạng thái ở gốc và trạng thái ở thành phần

Với yêu cầu `GET /actuator/health`, `status` ở ngoài cùng là kết quả tổng hợp cho các contributor thuộc phạm vi health đang được đánh giá.

Với `GET /actuator/health/inventory`, `status` ngoài cùng của phản hồi lại thuộc về riêng `inventory`. Nó không biến thành một phép kiểm tra toàn ứng dụng chỉ vì tên trường vẫn là `status`.

Do đó, hai yêu cầu này có thể đồng thời trả:

~~~text
GET /actuator/health            -> HTTP 503, status DOWN
GET /actuator/health/inventory  -> HTTP 200, status UP
~~~

Không có mâu thuẫn nếu bộ phận khác đang `DOWN`. Khi đọc một JSON health, trước tiên hãy xác định URL và phạm vi của nó.

### 2.2. Những trạng thái chuẩn

| Trạng thái | Cách hiểu |
| --- | --- |
| `UP` | Phép kiểm tra đánh giá bộ phận đang hoạt động theo tiêu chí của nó |
| `DOWN` | Phép kiểm tra phát hiện điều kiện không đạt |
| `OUT_OF_SERVICE` | Bộ phận được đánh giá đang ngoài trạng thái phục vụ |
| `UNKNOWN` | Không có kết luận trạng thái đã biết phù hợp |

`UP` chỉ có ý nghĩa trong giới hạn những gì đã được kiểm tra. Một indicator kiểm tra kết nối thành công không chứng minh mọi câu truy vấn hoặc mọi quy trình nghiệp vụ đều đúng.

`UNKNOWN` không có nghĩa “đã kiểm tra và chắc chắn tốt”. Nó cũng không tự đồng nghĩa với HTTP 503.

Các trạng thái không phải điểm số để cộng hoặc lấy trung bình. Với bộ tổng hợp mặc định của Spring Boot 3.3, thứ tự ưu tiên là:

~~~text
DOWN -> OUT_OF_SERVICE -> UP -> UNKNOWN
~~~

Trạng thái được ưu tiên trước trong số các trạng thái được nhận biết sẽ được chọn. Ví dụ:

| Các trạng thái con | Trạng thái tổng hợp mặc định |
| --- | --- |
| UP, UP | UP |
| UP, DOWN | DOWN |
| UP, OUT_OF_SERVICE | OUT_OF_SERVICE |
| UP, UNKNOWN | UP |
| UNKNOWN, UNKNOWN | UNKNOWN |

Đặc biệt, `UP` cùng `UNKNOWN` không mặc nhiên thành `UNKNOWN`. Nếu yêu cầu vận hành cần quy tắc khác, phải định nghĩa rõ thay vì suy ra từ tên tiếng Anh. Thứ tự mặc định có thể đối chiếu trong [SimpleStatusAggregator 3.3](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.java).

Ứng dụng có thể tạo trạng thái riêng như `DEGRADED`. Khi đó cần xét cả thứ tự tổng hợp lẫn ánh xạ HTTP; chỉ tạo một chuỗi trạng thái mới chưa làm hệ thống hiểu mức độ nghiêm trọng của nó.

### 2.3. status trong JSON khác mã HTTP

`status: "DOWN"` là dữ liệu của Actuator; `503` là mã của phản hồi HTTP.

Theo ánh xạ mặc định:

| Health status | HTTP |
| --- | --- |
| UP | 200 |
| DOWN | 503 |
| OUT_OF_SERVICE | 503 |
| UNKNOWN | 200 |

Hai quy tắc độc lập được thực hiện nối tiếp: tổng hợp health status, rồi ánh xạ trạng thái đó sang HTTP. Không suy luận mọi HTTP 200 đều có nghĩa nghiệp vụ sẵn sàng phục vụ.

Nếu tự cấu hình `status.http-mapping`, các ánh xạ mặc định cho DOWN và OUT_OF_SERVICE không còn được giữ tự động; cần khai báo lại nếu muốn giữ chúng. Quy tắc này nằm trong [tài liệu ánh xạ HTTP của health](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-health-indicators). API chịu trách nhiệm ánh xạ là [HttpCodeStatusMapper](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleHttpCodeStatusMapper.html).

401, 403 hoặc 404 lại có thể phản ánh quyền truy cập hay việc không tìm thấy tài nguyên; không coi chúng là những giá trị health status.

## 3. components là cấu trúc cây, không phải một danh sách cố định

`components` là một đối tượng JSON có các khóa là tên thành phần. Mỗi thành phần lại có `status`; một thành phần tổng hợp có thể có `components` của chính nó:

~~~json
{
  "status": "DOWN",
  "components": {
    "inventory": {
      "status": "UP"
    },
    "partners": {
      "status": "DOWN",
      "components": {
        "payments": {
          "status": "UP"
        },
        "courier": {
          "status": "DOWN"
        }
      }
    }
  }
}
~~~

Cây tương ứng:

~~~text
toàn hệ thống: DOWN
├── inventory: UP
└── partners: DOWN
    ├── payments: UP
    └── courier: DOWN
~~~

`partners` là một nút tổng hợp. Nó không có nghĩa indicator duy nhất đã gửi yêu cầu tới cả hai đối tác theo một thuật toán đặc biệt; trong ví dụ, nó chỉ tổ chức hai contributor con.

Trạng thái của `courier` đi vào phép tổng hợp của `partners`; trạng thái của `partners` lại đi vào phép tổng hợp ở gốc. Không đếm số nút UP rồi biểu quyết: ba nút UP không “thắng” một nút DOWN.

### Tên thành phần đến từ đâu?

Một `HealthIndicator` là phép kiểm tra trả về `Health`. `CompositeHealthContributor` tổ chức nhiều contributor con có tên. Đây là mô hình tạo cây, không phải các trường JSON do một controller tự ghép thủ công.

Với bean tên `inventoryHealthIndicator`, quy ước Spring Boot bỏ hậu tố `HealthIndicator`, nên ID là `inventory`. Với contributor tổng hợp, tên các con được xác định bởi cấu trúc đăng ký của nó. Khái niệm composite được mô tả trong [CompositeHealthContributor](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/CompositeHealthContributor.html).

Không giả định ứng dụng nào cũng có `db`, `redis`, `diskSpace` hoặc tên con cố định. Các mục xuất hiện phụ thuộc dependency, bean, cấu hình, registry và phạm vi health đang được hỏi. Đổi tên bean cũng có thể làm đường dẫn và hợp đồng mà phần mềm giám sát đang dùng thay đổi.

### Đừng nhầm component với health group

Component là một nút trong cây contributor. Health group là một góc nhìn chọn tập contributor để phục vụ mục đích riêng. Cả hai có thể dùng URL nằm dưới `/actuator/health`, nhưng không phải một khái niệm.

Nếu phản hồi có thêm trường `groups`, đó là thông tin về các group được cấu hình, không phải nội dung thay thế cho `components`. Việc đọc liveness/readiness phải dựa vào đúng group và tiêu chí của group đó; không suy ra từ mọi giá trị UP ở một URL bất kỳ.

## 4. details là dữ liệu giải thích, không tham gia tổng hợp một cách tự động

Một nút lá thường có `status` và có thể có `details`:

~~~json
{
  "status": "DOWN",
  "details": {
    "reason": "simulated timeout",
    "region": "lab"
  }
}
~~~

Các khóa `reason`, `region`, `availableItems`, `database` hoặc `threshold` không phải bộ trường chung mà mọi health response phải có. Indicator nào cung cấp dữ liệu gì thì hợp đồng chi tiết của indicator đó quyết định.

`details` có thể chứa chuỗi, số, boolean, mảng hoặc đối tượng có thể tuần tự hóa phù hợp. Nó có thể không xuất hiện vì không có dữ liệu hoặc vì chính sách không cho hiện. Không buộc mọi nút phải có `details: {}`.

### Một chữ DOWN trong details không làm trạng thái thành DOWN

Xét kết quả sau:

~~~json
{
  "status": "UP",
  "details": {
    "reportedStatus": "DOWN"
  }
}
~~~

Về cấu trúc, đây vẫn là một Health có trạng thái `UP`. `reportedStatus` chỉ là dữ liệu do người viết indicator đặt tên. Bộ tổng hợp không duyệt mọi chuỗi ở mọi cấp JSON để tìm từ DOWN.

Mã tạo ra trạng thái thật phải dùng builder hoặc cơ chế tương đương, chẳng hạn `Health.down()`. Nếu đã phát hiện lỗi nhưng vẫn trả `Health.up().withDetail("error", "...")`, chính indicator đang báo sai trạng thái, không phải Actuator bỏ qua một trường có ý nghĩa chuẩn.

Tương tự, đặt một map có tên `components` bên trong `details` không tạo ra các contributor con. Muốn có cây health thật cần đăng ký contributor/composite. Lớp [Health](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/Health.html) tách rõ status và map details.

### Dữ liệu giải thích cũng có thể nhạy cảm

Đường dẫn tệp, tên máy, lỗi kết nối và thông báo exception có thể giúp điều tra nhưng cũng tiết lộ hạ tầng. Không đưa mật khẩu, access token, nội dung người dùng hoặc toàn bộ cấu hình vào details.

Ẩn details là chính sách trình bày kết quả. Nó không biến một phép kiểm tra sai thành đúng, không tắt indicator và không sửa những bí mật đã bị ghi vào log.

## 5. Vì sao có lúc chỉ nhìn thấy status?

Hai thuộc tính riêng điều khiển mức thông tin trả về:

- `management.endpoint.health.show-components`: có hiện cấu trúc các thành phần hay không.
- `management.endpoint.health.show-details`: có hiện dữ liệu giải thích của các kết quả hay không.

Các giá trị chính là `never`, `always`, `when-authorized`. Để thấy rõ ý định và tránh phụ thuộc vào giá trị suy ra giữa các thiết lập, bài thử đặt tường minh cả hai.

| show-components | show-details | Góc nhìn minh họa ở URL gốc |
| --- | --- | --- |
| never | never | Chỉ trạng thái tổng thể |
| always | never | Cây thành phần và trạng thái, không có details |
| always | always | Cây thành phần cùng dữ liệu giải thích nếu có |
| when-authorized | when-authorized | Mức thông tin phụ thuộc người gọi được phép hay không |

Ví dụ chỉ trả:

~~~json
{
  "status": "DOWN"
}
~~~

Điều đó không có nghĩa hệ thống không có contributor hoặc indicator không chạy. Kết quả lỗi vẫn được tính, chỉ có cây và dữ liệu giải thích bị ẩn.

Với `when-authorized`, cần xét `management.endpoint.health.roles`; nếu không đặt roles, mọi người đã xác thực có thể được xem là được phép. Chính sách hiện thông tin không thay thế quy tắc cho phép truy cập URL của Spring Security.

Trong Boot 3.3, nếu không được hiện components, yêu cầu trực tiếp tới đường dẫn component cũng không đơn giản là “đi vòng để xem chi tiết”: endpoint không cung cấp kết quả cho đường dẫn con đó. Ví dụ trong bài, `/actuator/health/inventory` sẽ trả 404 khi `show-components: never`, dù indicator tồn tại. Có thể đối chiếu điều kiện xử lý đường dẫn trong [HealthEndpointSupport 3.3](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointSupport.java).

Khi có thêm lớp bảo mật hoặc proxy, mã trả về có thể bị thay đổi trước khi đến endpoint. Vì vậy, 404 là một dấu hiệu cần kiểm tra cùng cấu hình, không phải bằng chứng duy nhất rằng bean không tồn tại.

## 6. Thực hành: một nút đơn và một nhánh tổng hợp

Mục tiêu là nhìn thấy cùng một bộ kiểm tra dưới ba mức hiển thị, rồi quan sát lỗi ở một lá đi lên nút cha. Không cần cơ sở dữ liệu hay dịch vụ bên ngoài; mọi kết quả là dữ liệu mô phỏng ổn định.

### 6.1. Chuẩn bị dự án

Dùng một dự án Spring Boot 3.3.x tối thiểu có plugin Spring Boot, dependency management, Java 21 và Gradle Wrapper. Phần dependency cần có:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Ví dụ này không thêm Spring Security; ứng dụng chỉ lắng nghe loopback và chỉ công bố health. Nếu bổ sung vào dự án đã có bảo mật, phải đáp ứng chính sách truy cập của dự án đó.

Tạo `src/main/java/com/example/healthshape/HealthShapeApplication.java`:

~~~java
package com.example.healthshape;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HealthShapeApplication {
    public static void main(String[] args) {
        SpringApplication.run(HealthShapeApplication.class, args);
    }
}
~~~

Tạo `src/main/java/com/example/healthshape/LabHealthContributors.java`:

~~~java
package com.example.healthshape;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.health.CompositeHealthContributor;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LabHealthContributors {
    @Bean
    HealthIndicator inventoryHealthIndicator() {
        return () -> Health.up()
            .withDetail("availableItems", 12)
            .withDetail("source", "simulated")
            .build();
    }

    @Bean
    CompositeHealthContributor partners(
            @Value("${lab.courier-down:false}") boolean courierDown) {
        HealthIndicator payments = () -> Health.up()
            .withDetail("provider", "sandbox")
            .build();

        HealthIndicator courier = () -> {
            if (courierDown) {
                return Health.down()
                    .withDetail("reason", "simulated timeout")
                    .withDetail("region", "lab")
                    .build();
            }
            return Health.up()
                .withDetail("region", "lab")
                .build();
        };

        return CompositeHealthContributor.fromMap(Map.of(
            "payments", payments,
            "courier", courier
        ));
    }
}
~~~

Bean `inventoryHealthIndicator` thành ID `inventory`; bean `partners` là nhánh tổng hợp. Hai biến `payments` và `courier` không được đăng ký thành các bean health độc lập ở gốc; chúng được đưa vào bên trong composite.

`courierDown` được đọc khi tạo bean. Đổi biến môi trường sau lúc chạy không tự cập nhật giá trị trong ví dụ; hãy khởi động lại với cấu hình mới.

### 6.2. Cấu hình góc nhìn tóm tắt

`src/main/resources/application.yml`:

~~~yaml
server:
  address: 127.0.0.1

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-components: never
      show-details: never
      probes:
        enabled: false
  health:
    defaults:
      enabled: false

lab:
  courier-down: false
~~~

Tắt các indicator tự cấu hình mặc định giúp ví dụ không phụ thuộc dung lượng đĩa hay các dependency ngoài. Nó không xóa hai contributor do bài tự khai báo. Các probe group tự động cũng được tắt để tập trung quan sát cây đang học.

Chạy từ PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Ở terminal khác:

~~~powershell
$response = Invoke-WebRequest -UseBasicParsing `
    -Uri 'http://127.0.0.1:8080/actuator/health' `
    -Headers @{ Accept = 'application/vnd.spring-boot.actuator.v3+json' }
$response.StatusCode
$response.Content | ConvertFrom-Json | ConvertTo-Json -Depth 10
~~~

Mã HTTP là `200`; nội dung JSON có ý nghĩa tương đương:

~~~json
{
  "status": "UP"
}
~~~

Cách thụt lề và thứ tự khóa không phải một phần của kết quả cần khẳng định.

### 6.3. Mở cây và thông tin giải thích trong profile cục bộ

Tạo `src/main/resources/application-health-tree.yml`:

~~~yaml
management:
  endpoint:
    health:
      show-components: always
      show-details: always
~~~

Dừng lần chạy cũ bằng Ctrl+C rồi chạy:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=health-tree"
~~~

Gọi lại URL health với Accept V3. Khi `lab.courier-down=false`, kết quả JSON là:

~~~json
{
  "status": "UP",
  "components": {
    "inventory": {
      "status": "UP",
      "details": {
        "availableItems": 12,
        "source": "simulated"
      }
    },
    "partners": {
      "status": "UP",
      "components": {
        "payments": {
          "status": "UP",
          "details": {
            "provider": "sandbox"
          }
        },
        "courier": {
          "status": "UP",
          "details": {
            "region": "lab"
          }
        }
      }
    }
  }
}
~~~

Thứ tự `payments` và `courier` không được bảo đảm bởi ví dụ dùng `Map.of`; hãy kiểm tra theo khóa, không so sánh chuỗi JSON theo thứ tự.

Có thể truy vấn từng phạm vi:

| URL | Dạng kết quả |
| --- | --- |
| `/actuator/health` | Trạng thái gốc và components |
| `/actuator/health/inventory` | Trạng thái inventory và details của nó |
| `/actuator/health/partners` | Trạng thái partners và components con |
| `/actuator/health/partners/courier` | Trạng thái courier và details của nó |

URL lá không bọc lại toàn bộ đường đi cha. Với courier đang UP, nó trả:

~~~json
{
  "status": "UP",
  "details": {
    "region": "lab"
  }
}
~~~

### 6.4. Giữ cây nhưng bỏ details

Dừng lần chạy trước và khởi động lại:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=health-tree --management.endpoint.health.show-details=never"
~~~

Lúc này root vẫn có inventory và partners cùng các trạng thái; trường details của các lá không xuất hiện. Việc các lá hết details không chứng minh chúng ngừng kiểm tra.

Truy vấn `/actuator/health/inventory` vẫn có kết quả vì `show-components=always`, nhưng nội dung chỉ còn:

~~~json
{
  "status": "UP"
}
~~~

### 6.5. Làm một lá DOWN

Khởi động lại với:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=health-tree --lab.courier-down=true"
~~~

Khi đó:

~~~text
/actuator/health                   -> HTTP 503, status DOWN
/actuator/health/partners          -> HTTP 503, status DOWN
/actuator/health/partners/courier  -> HTTP 503, status DOWN
/actuator/health/inventory         -> HTTP 200, status UP
~~~

Phản hồi riêng courier là:

~~~json
{
  "status": "DOWN",
  "details": {
    "reason": "simulated timeout",
    "region": "lab"
  }
}
~~~

Các lệnh `Invoke-WebRequest` có thể ném lỗi khi nhận 503. Có thể quan sát cả header lẫn body mà không bị PowerShell chuyển sang nhánh exception bằng curl thật:

~~~powershell
curl.exe -i `
    -H "Accept: application/vnd.spring-boot.actuator.v3+json" `
    http://127.0.0.1:8080/actuator/health
~~~

Đọc dòng trạng thái HTTP và trường status trong body riêng biệt. Không dùng `curl` không có đuôi `.exe` rồi mặc định mọi phiên PowerShell đều gọi cùng một chương trình.

Cuối cùng, chạy lại chế độ tóm tắt với lỗi vẫn còn:

~~~powershell
.\gradlew.bat bootRun --args="--lab.courier-down=true"
~~~

Root trả HTTP 503 với `{"status":"DOWN"}`. Cây bị ẩn, nhưng lỗi vẫn ảnh hưởng kết quả tổng hợp. Đây là phép thử trực tiếp rằng **chính sách hiển thị không phải chính sách tính trạng thái**.

## 7. Kiểm thử hợp đồng cấu trúc thay vì thứ tự JSON

Các tệp kiểm thử dưới đây đặt trong `src/test/java/com/example/healthshape/`. Chúng dùng MockMvc để kiểm tra schema và phạm vi, không gọi dịch vụ bên ngoài.

### 7.1. Cây đầy đủ với một lá lỗi

`HealthTreeTest.java`:

~~~java
package com.example.healthshape;

import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.SimpleStatusAggregator;
import org.springframework.boot.actuate.health.Status;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "management.endpoint.health.show-components=always",
    "management.endpoint.health.show-details=always",
    "lab.courier-down=true"
})
@AutoConfigureMockMvc
class HealthTreeTest {
    private static final String V3 =
        "application/vnd.spring-boot.actuator.v3+json";

    @Autowired MockMvc mvc;

    @Test
    void failureFlowsFromLeafToRoot() throws Exception {
        mvc.perform(get("/actuator/health").accept(V3))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.status").value("DOWN"))
            .andExpect(jsonPath("$.components.inventory.status").value("UP"))
            .andExpect(jsonPath("$.components.partners.status").value("DOWN"))
            .andExpect(jsonPath(
                "$.components.partners.components.courier.status"
            ).value("DOWN"))
            .andExpect(jsonPath(
                "$.components.partners.components.courier.details.reason"
            ).value("simulated timeout"));
    }

    @Test
    void healthyLeafKeepsItsOwnScope() throws Exception {
        mvc.perform(get("/actuator/health/inventory").accept(V3))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("UP"))
            .andExpect(jsonPath("$.details.availableItems").value(12))
            .andExpect(jsonPath("$.components").doesNotExist());
    }

    @Test
    void compositeEndpointReturnsItsChildren() throws Exception {
        mvc.perform(get("/actuator/health/partners").accept(V3))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.status").value("DOWN"))
            .andExpect(jsonPath("$.components.courier.status").value("DOWN"))
            .andExpect(jsonPath("$.components.payments.status").value("UP"));
    }

    @Test
    void aDetailValueDoesNotChangeActualStatus() {
        Health health = Health.up()
            .withDetail("reportedStatus", "DOWN")
            .build();

        assertEquals(Status.UP, health.getStatus());
        assertEquals(Status.UP, new SimpleStatusAggregator()
            .getAggregateStatus(Set.of(health.getStatus())));
    }
}
~~~

### 7.2. Chỉ hiện trạng thái tổng thể

`HealthSummaryTest.java`:

~~~java
package com.example.healthshape;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "management.endpoint.health.show-components=never",
    "management.endpoint.health.show-details=never",
    "lab.courier-down=true"
})
@AutoConfigureMockMvc
class HealthSummaryTest {
    @Autowired MockMvc mvc;

    @Test
    void hidingStructureDoesNotHideFailureStatus() throws Exception {
        mvc.perform(get("/actuator/health"))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.status").value("DOWN"))
            .andExpect(jsonPath("$.components").doesNotExist())
            .andExpect(jsonPath("$.details").doesNotExist());
    }

    @Test
    void componentPathIsUnavailableWhenComponentsAreHidden()
            throws Exception {
        mvc.perform(get("/actuator/health/inventory"))
            .andExpect(status().isNotFound());
    }
}
~~~

### 7.3. Hiện cây nhưng ẩn dữ liệu giải thích

`HealthComponentsOnlyTest.java`:

~~~java
package com.example.healthshape;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "management.endpoint.health.show-components=always",
    "management.endpoint.health.show-details=never",
    "lab.courier-down=true"
})
@AutoConfigureMockMvc
class HealthComponentsOnlyTest {
    @Autowired MockMvc mvc;

    @Test
    void statusesRemainVisibleWithoutDetails() throws Exception {
        mvc.perform(get("/actuator/health"))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.components.inventory.status").value("UP"))
            .andExpect(jsonPath(
                "$.components.inventory.details"
            ).doesNotExist())
            .andExpect(jsonPath(
                "$.components.partners.components.courier.status"
            ).value("DOWN"))
            .andExpect(jsonPath(
                "$.components.partners.components.courier.details"
            ).doesNotExist());
    }

    @Test
    void leafPathWorksWithoutDetails() throws Exception {
        mvc.perform(get("/actuator/health/partners/courier"))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.status").value("DOWN"))
            .andExpect(jsonPath("$.details").doesNotExist());
    }
}
~~~

Chạy tám kiểm thử:

~~~powershell
.\gradlew.bat test --tests "com.example.healthshape.Health*Test"
~~~

Kỳ vọng cả tám đạt với đúng dự án tối thiểu đã mô tả. Các test không cố định thứ tự khóa, dung lượng đĩa, nội dung log khởi động hay trạng thái dịch vụ bên ngoài.

Nếu áp dụng test vào dự án có Spring Security, group riêng hoặc contributor bổ sung, cần đối chiếu khác biệt trước khi kết luận Actuator trả sai.

## 8. Cách phần mềm giám sát nên đọc phản hồi

Một trình đọc health cần biết mình cần mức kết luận nào:

1. Xác định đúng endpoint và phạm vi: toàn hệ thống, group hay component.
2. Đọc mã HTTP theo hợp đồng đã cấu hình.
3. Đọc status thật của nút tương ứng.
4. Nếu cần chẩn đoán, đi xuống components theo tên và xử lý trường không tồn tại.
5. Chỉ đọc details theo hợp đồng của từng indicator; không giả định một schema chi tiết dùng cho mọi nút.

Không so sánh toàn bộ response như một chuỗi. Thứ tự khóa JSON không mang ý nghĩa cây hoặc mức nghiêm trọng. Một trình đọc bền vững cần phân biệt:

- Có trường status và giá trị là UNKNOWN.
- Không được hiện components.
- Component đích không còn được đăng ký.
- Không được truy cập endpoint.
- Không nhận được phản hồi do lỗi kết nối hoặc timeout.

Không có response không phải là response `{"status":"DOWN"}`. Đó là một tín hiệu vận hành khác cần được hệ thống giám sát xử lý rõ.

Một lần nhận UP cũng không phải bảo đảm vĩnh viễn. Kết quả phản ánh phép đánh giá trong phạm vi đã chọn; tải, kết nối hoặc dữ liệu có thể thay đổi sau đó. Nếu cấu hình cache ở endpoint/proxy, còn cần xét độ mới của dữ liệu.

## 9. Những nhầm lẫn thường gặp

| Nhận định | Điều cần sửa |
| --- | --- |
| Root UP nghĩa là mọi nghiệp vụ đã được kiểm chứng | UP chỉ dựa vào những contributor thuộc phạm vi và tiêu chí đang dùng |
| `components` là một mảng | Nó là object có tên thành phần làm khóa |
| Mọi nút đều phải có details | Details có thể trống, không được tạo hoặc bị ẩn |
| Nút tổng hợp phải có details của mọi con | Thông tin từng con nằm ở cây components tương ứng |
| Ẩn details làm lỗi không ảnh hưởng root | Việc tổng hợp status vẫn diễn ra |
| HTTP 200 luôn tương đương status UP | UNKNOWN mặc định cũng ánh xạ 200; có thể có mapping tùy chỉnh |
| Có nhiều nút UP thì root phải UP | Bộ tổng hợp theo thứ tự trạng thái, không biểu quyết |
| Một chuỗi DOWN trong details tự làm root DOWN | Chỉ status thật của kết quả health tham gia tổng hợp |
| Không thấy `db` nghĩa là database chắc chắn hỏng | Có thể chưa có indicator, bị tắt hoặc không thuộc phạm vi |
| Component URL luôn truy cập được nếu đoán đúng tên | Còn phụ thuộc việc hiện components và các lớp bảo mật |
| Liveness, readiness và health gốc luôn cùng nghĩa | Phạm vi và mục đích của chúng có thể khác nhau |

Khi chẩn đoán, hãy hỏi lần lượt: URL nào, contributor nào, chính sách hiển thị nào, bộ tổng hợp nào và mapping HTTP nào. Không chữa một trường vắng mặt bằng cách mở toàn bộ details trước khi hiểu nguyên nhân.

## 10. Tự kiểm tra

1. Trong cây partners, chỉ courier DOWN: status của partners và root là gì theo mặc định?
2. Vì sao inventory vẫn trả HTTP 200 khi root trả 503?
3. Root chỉ hiện `{"status":"DOWN"}`: có thể kết luận không có components không?
4. `details.reportedStatus` là DOWN nhưng status ngoài cùng là UP: bộ tổng hợp dùng giá trị nào?
5. Muốn hiện tên các thành phần và trạng thái nhưng không hiện đường dẫn hoặc lỗi chi tiết thì chọn cấu hình nào?
6. Vì sao test dùng JSONPath theo khóa phù hợp hơn so sánh nguyên chuỗi JSON?
7. Khi nhận 404 ở component URL, cần kiểm tra những điều kiện nào ngoài việc bean có tồn tại?

Mục tiêu là đọc được ba lớp thông tin riêng biệt: **status đưa ra kết luận tại một nút, components mô tả cấu trúc các nút con, details cung cấp dữ liệu giải thích mà không tự quyết định kết luận**.

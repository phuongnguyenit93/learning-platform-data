# Tổng hợp trạng thái bằng StatusAggregator

## 1. Từ nhiều kết quả kiểm tra đến một trạng thái chung

Một ứng dụng có thể kiểm tra cơ sở dữ liệu, bộ nhớ đệm và dịch vụ đối tác. Mỗi phép kiểm tra trả về một trạng thái, nhưng phần mềm giám sát thường cần một kết luận cho toàn hệ thống hoặc một nhóm kiểm tra.

Giả sử các kết quả là:

~~~text
storage: UP
cache: UP
partner: DOWN
~~~

Câu hỏi cần giải quyết không phải “có bao nhiêu chữ UP trong JSON”, mà là: **với chính sách sức khỏe đã chọn, tập trạng thái này phải được kết luận như thế nào?**

`StatusAggregator` là chiến lược tổng hợp các `Status` thành một `Status`. Trong quy trình health, nó đứng sau việc thực hiện kiểm tra và trước việc ánh xạ kết quả ra mã HTTP:

~~~text
HealthIndicator thực hiện kiểm tra
        ↓
Health mang status của từng thành phần
        ↓
StatusAggregator chọn status tổng hợp
        ↓
HttpCodeStatusMapper chọn mã HTTP
        ↓
Health endpoint trả phản hồi
~~~

Bài dùng **Spring Boot 3.3.x và Java 21**. Các ví dụ trạng thái tùy chỉnh là chính sách do bài định nghĩa, không phải trạng thái hoặc quy tắc mặc định mà Spring Boot tự áp dụng.

## 2. Hợp đồng của StatusAggregator: đầu vào là một tập trạng thái

Phương thức cốt lõi có dạng:

~~~java
Status getAggregateStatus(Set<Status> statuses);
~~~

Đây là chữ ký minh họa của interface, không phải một tệp Java chạy độc lập.

`Status` là đối tượng biểu diễn trạng thái, có các hằng như `UP`, `DOWN`, `OUT_OF_SERVICE`, `UNKNOWN`; nó cũng cho phép tạo mã riêng bằng `new Status("DEGRADED")`. Nó không phải một enum chỉ chứa bốn giá trị cố định. Xem [API Status 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/Status.html).

### 2.1. Bộ tổng hợp không nhận đầy đủ Health

Đầu vào không chứa tên bean, thời gian kiểm tra, exception, URL dịch vụ hay map details. Vì vậy, bộ tổng hợp thông thường không biết DOWN đến từ database hay một dịch vụ phụ.

Nếu cần chính sách “database bắt buộc, dịch vụ gợi ý có thể lỗi”, hãy thể hiện phạm vi đó bằng nhóm health, cấu trúc contributor hoặc một phép kiểm tra chuyên trách. Không cố suy ngược danh tính từ tập trạng thái đã mất thông tin.

### 2.2. Set không giữ số phiếu

Ví dụ:

~~~text
UP, UP, UP, DOWN
        ↓
Set chứa UP và DOWN
~~~

Đầu vào đó không cho biết có ba thành phần UP hay ba nghìn thành phần UP. Nó cũng không giữ thứ tự đăng ký bean.

Do đó, không thể dùng riêng hợp đồng này để tính đúng một chính sách đa số hoặc “ít nhất 2 trong 3 máy còn khỏe”. Một indicator chuyên trách có thể biết danh sách máy, đếm kết quả và trả một trạng thái cuối cùng; sau đó trạng thái ấy mới đi vào bộ tổng hợp chung.

Interface còn có phương thức tiện ích nhận nhiều `Status`, nhưng cuối cùng cũng chuyển về tập để tổng hợp; xem [mã nguồn StatusAggregator 3.3](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/StatusAggregator.java).

### 2.3. Đây là chính sách kết luận, không phải nơi kiểm tra mạng

Bộ tổng hợp không nên gọi lại database hoặc gửi yêu cầu HTTP để xác minh từng status. Indicator chịu trách nhiệm thực hiện phép kiểm tra; aggregator xử lý các kết quả đã có.

Một triển khai phù hợp nên có kết quả xác định, không phụ thuộc thứ tự duyệt Set, không sửa Set đầu vào và không giữ trạng thái thay đổi giữa các yêu cầu. Điều này cũng giúp hành vi dễ kiểm thử khi nhiều yêu cầu health diễn ra đồng thời.

## 3. SimpleStatusAggregator mặc định làm gì?

Spring Boot cung cấp `SimpleStatusAggregator`, dùng một danh sách ưu tiên trạng thái. Với Boot 3.3, thứ tự mặc định là:

~~~text
DOWN → OUT_OF_SERVICE → UP → UNKNOWN
~~~

Đây là thứ tự do chính sách định nghĩa, không phải thứ tự chữ cái và cũng không phải thứ tự các indicator chạy.

Cách đọc thuật toán:

1. Xét các trạng thái có mặt trong tập đầu vào.
2. Chỉ giữ những mã được danh sách thứ tự nhận biết.
3. Chọn trạng thái có vị trí ưu tiên trước nhất.
4. Nếu không còn trạng thái được nhận biết, trả `UNKNOWN`.

Không cần tất cả trạng thái trong danh sách đều xuất hiện. Chỉ cần một DOWN thì DOWN được ưu tiên trước những giá trị chuẩn còn lại.

| Tập đầu vào | Kết quả mặc định |
| --- | --- |
| UP | UP |
| UP, DOWN | DOWN |
| UP, OUT_OF_SERVICE | OUT_OF_SERVICE |
| DOWN, OUT_OF_SERVICE | DOWN |
| UP, UNKNOWN | UP |
| UNKNOWN | UNKNOWN |
| Tập rỗng khi gọi trực tiếp aggregator | UNKNOWN |

Hai điểm đáng chú ý:

- UNKNOWN đứng sau UP trong mặc định. Nó không tự làm kết quả UP đổi thành UNKNOWN.
- Quy tắc cho tập rỗng là kết quả của lời gọi trực tiếp tới aggregator. Không suy rộng rằng health endpoint không có contributor nhất định phải trả cùng kết quả; endpoint còn có logic xử lý trường hợp không có đóng góp.

Cơ chế lựa chọn và thứ tự mặc định có thể đối chiếu trong [SimpleStatusAggregator 3.3](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.java). Các constructor nhận danh sách hoặc các mã theo thứ tự nằm trong [API SimpleStatusAggregator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.html).

## 4. UNKNOWN khác một mã chưa được bộ tổng hợp nhận biết

Đây là khác biệt quan trọng:

- `Status.UNKNOWN` là một trạng thái chuẩn có trong danh sách mặc định.
- `new Status("DEGRADED")` là một mã riêng; mặc định chưa có vị trí cho nó.

Với bộ tổng hợp mặc định:

| Tập đầu vào | Kết quả | Lý do |
| --- | --- | --- |
| UP, DEGRADED | UP | DEGRADED không được nhận biết, UP còn lại |
| DEGRADED | UNKNOWN | Không có mã nào trong danh sách được nhận biết |
| DOWN, DEGRADED | DOWN | DOWN được nhận biết và ưu tiên |
| UP, MYSTERY | UP | Mã chưa biết không tự trở thành lỗi nghiêm trọng |

Bộ tổng hợp không tự hiểu nghĩa của từ DEGRADED hoặc FATAL. Một từ nghe nghiêm trọng với con người không làm framework tự gán mức độ nghiêm trọng.

Hệ quả thực tế: indicator có thể hiển thị `status: "DEGRADED"` ở component, trong khi root vẫn là UP vì còn một component UP khác. Muốn thay đổi kết luận chung, phải cấu hình thứ tự hoặc cung cấp bộ tổng hợp phù hợp.

Nên thống nhất mã trạng thái trong chương trình, chẳng hạn dùng chữ hoa và dấu gạch dưới cho mã chuẩn. Không dựa vào thứ tự chữ cái hay việc đổi cách viết để biểu diễn độ nghiêm trọng.

## 5. Cấu hình thứ tự: giữ rõ những trạng thái cần xét

Nếu yêu cầu là “DEGRADED cần được ưu tiên hơn UP và UNKNOWN cũng không bị UP che”, có thể dùng:

~~~yaml
management:
  endpoint:
    health:
      status:
        order:
          - down
          - out-of-service
          - degraded
          - unknown
          - up
~~~

Danh sách này là **một chính sách mới**. So với mặc định, UNKNOWN đã được đưa lên trước UP; đây là lựa chọn có chủ đích, không phải bản chép lại mặc định.

Kết quả theo danh sách trên:

| Đầu vào | Kết quả |
| --- | --- |
| UP, DEGRADED | DEGRADED |
| UP, UNKNOWN | UNKNOWN |
| DEGRADED, UNKNOWN | DEGRADED |
| DOWN, DEGRADED | DOWN |
| UP, MYSTERY | UP |

Hàng cuối vẫn cần chú ý: MYSTERY không có trong danh sách mới nên vẫn không được nhận biết.

Danh sách cấu hình không phải yêu cầu “thêm một mục rồi giữ nguyên mọi mục mặc định”. Một danh sách ngắn như chỉ có `degraded,up` sẽ bỏ DOWN và OUT_OF_SERVICE khỏi tập mã được lựa chọn theo danh sách đó. Nếu có UP cùng DOWN, chính sách thiếu DOWN có thể kết luận UP.

Hãy khai báo đủ các mã mà chính sách cần hiểu, rồi kiểm thử cả trạng thái chuẩn lẫn tùy chỉnh. Không chỉ thử trường hợp DEGRADED mà quên kiểm tra DOWN.

## 6. Thứ tự trạng thái và mã HTTP là hai cấu hình khác nhau

Sau khi tổng hợp ra DEGRADED, HTTP chưa tự đổi thành 503. Mặc định DOWN và OUT_OF_SERVICE được ánh xạ 503; những mã không có ánh xạ thường dùng 200, gồm UNKNOWN và mã tùy chỉnh.

Nếu muốn DEGRADED trả 503 và giữ ánh xạ lỗi chuẩn:

~~~yaml
management:
  endpoint:
    health:
      status:
        http-mapping:
          down: 503
          out-of-service: 503
          degraded: 503
~~~

Khi khai báo ánh xạ tùy chỉnh, phải giữ lại DOWN và OUT_OF_SERVICE nếu muốn bảo toàn hành vi mặc định. Chỉ khai báo `degraded: 503` có thể khiến hai trạng thái chuẩn không còn ánh xạ 503 như trước.

Hai cấu hình giải quyết hai câu hỏi:

| Cấu hình | Câu hỏi |
| --- | --- |
| `status.order` | Trong các kết quả con, kết luận health nào được chọn? |
| `status.http-mapping` | Khi đã có kết luận ấy, HTTP phải trả mã nào? |

Đặt `http-mapping.degraded=503` không làm DEGRADED tự được ưu tiên trước UP. Ngược lại, đưa DEGRADED lên đầu danh sách không tự cấp cho nó mã HTTP 503.

UNKNOWN mặc định vẫn có thể trả 200 ngay khi chính sách tổng hợp thận trọng chọn UNKNOWN. Nếu quyết định UNKNOWN không được xem là sẵn sàng phục vụ, phải xét thêm ánh xạ HTTP và cách phần mềm giám sát sử dụng kết quả.

Thứ tự, mã tùy chỉnh và quy tắc giữ lại ánh xạ mặc định được mô tả trong [hướng dẫn health của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-health-indicators).

## 7. Chương trình nhỏ để quan sát thuật toán

Ví dụ này chỉ gọi lớp tổng hợp, không khởi động web server và không thực hiện kiểm tra mạng.

Trong một dự án Gradle đã có plugin Java, plugin Spring Boot 3.3.x và dependency management, cần dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Tạo `src/main/java/com/example/aggregation/AggregatorConsoleDemo.java`:

~~~java
package com.example.aggregation;

import java.util.Set;

import org.springframework.boot.actuate.health.SimpleStatusAggregator;
import org.springframework.boot.actuate.health.Status;
import org.springframework.boot.actuate.health.StatusAggregator;

public class AggregatorConsoleDemo {
    public static void main(String[] args) {
        StatusAggregator defaults = new SimpleStatusAggregator();
        StatusAggregator ordered = new SimpleStatusAggregator(
            "DOWN", "OUT_OF_SERVICE", "DEGRADED", "UNKNOWN", "UP"
        );
        Status degraded = new Status("DEGRADED");

        System.out.println("default UP+DOWN = " +
            defaults.getAggregateStatus(Set.of(Status.UP, Status.DOWN)).getCode());
        System.out.println("default UP+UNKNOWN = " +
            defaults.getAggregateStatus(Set.of(Status.UP, Status.UNKNOWN)).getCode());
        System.out.println("default UP+DEGRADED = " +
            defaults.getAggregateStatus(Set.of(Status.UP, degraded)).getCode());
        System.out.println("default DEGRADED = " +
            defaults.getAggregateStatus(Set.of(degraded)).getCode());
        System.out.println("ordered UP+DEGRADED = " +
            ordered.getAggregateStatus(Set.of(Status.UP, degraded)).getCode());
        System.out.println("ordered UP+UNKNOWN = " +
            ordered.getAggregateStatus(Set.of(Status.UP, Status.UNKNOWN)).getCode());
        System.out.println("default empty = " +
            defaults.getAggregateStatus(Set.<Status>of()).getCode());
    }
}
~~~

Thêm tác vụ chạy vào `build.gradle`:

~~~groovy
tasks.register('runAggregatorDemo', JavaExec) {
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'com.example.aggregation.AggregatorConsoleDemo'
}
~~~

Chạy từ PowerShell:

~~~powershell
.\gradlew.bat runAggregatorDemo --quiet
~~~

Các dòng do chương trình in ra:

~~~text
default UP+DOWN = DOWN
default UP+UNKNOWN = UP
default UP+DEGRADED = UP
default DEGRADED = UNKNOWN
ordered UP+DEGRADED = DEGRADED
ordered UP+UNKNOWN = UNKNOWN
default empty = UNKNOWN
~~~

Đây là mã dùng thư viện Spring Boot, nên lệnh javac không có classpath Actuator sẽ không đủ. Tác vụ JavaExec lấy classpath từ dependency của dự án.

## 8. Khi nào cần viết StatusAggregator riêng?

Danh sách thứ tự phù hợp khi yêu cầu là ưu tiên các mã đã biết. Nếu cần một quy tắc khác, chẳng hạn “mọi mã chưa được nhận biết phải khiến kết quả thành UNKNOWN, thay vì bị UP che”, có thể viết triển khai riêng.

Chính sách ví dụ sau:

1. Tập rỗng → UNKNOWN.
2. Có DOWN → DOWN.
3. Có OUT_OF_SERVICE → OUT_OF_SERVICE.
4. Có mã ngoài danh sách đã biết hoặc có UNKNOWN → UNKNOWN.
5. Có DEGRADED → DEGRADED.
6. Các trường hợp còn lại, với tập không rỗng và chỉ chứa mã đã biết → UP.

Đây là chính sách của bài, không phải chuẩn bắt buộc cho mọi hệ thống. Với DOWN cùng một mã lạ, DOWN vẫn được chọn theo bước 2. Với DEGRADED cùng UNKNOWN, UNKNOWN được chọn; điều này khác danh sách của phần trước.

`ConservativeStatusAggregator.java`:

~~~java
package com.example.aggregation;

import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.boot.actuate.health.Status;
import org.springframework.boot.actuate.health.StatusAggregator;

public final class ConservativeStatusAggregator implements StatusAggregator {
    private static final Set<String> KNOWN_CODES = Set.of(
        "DOWN", "OUT_OF_SERVICE", "UNKNOWN", "DEGRADED", "UP"
    );

    @Override
    public Status getAggregateStatus(Set<Status> statuses) {
        if (statuses.isEmpty()) {
            return Status.UNKNOWN;
        }

        Set<String> codes = statuses.stream()
            .map(Status::getCode)
            .collect(Collectors.toSet());

        if (codes.contains("DOWN")) {
            return Status.DOWN;
        }
        if (codes.contains("OUT_OF_SERVICE")) {
            return Status.OUT_OF_SERVICE;
        }
        if (!KNOWN_CODES.containsAll(codes) || codes.contains("UNKNOWN")) {
            return Status.UNKNOWN;
        }
        if (codes.contains("DEGRADED")) {
            return new Status("DEGRADED");
        }
        return Status.UP;
    }
}
~~~

Các mã trong triển khai này được so sánh theo chuỗi chữ hoa đã thống nhất. Nó không tự dùng các quy tắc chuẩn hóa mã của SimpleStatusAggregator. Nếu hệ thống nhận nhiều cách viết, phải định nghĩa và kiểm thử việc chuẩn hóa thay vì mặc định hai triển khai có hành vi giống nhau.

Không trả null khi không biết kết quả; dùng trạng thái có nghĩa rõ. Đầu vào của ví dụ phải là Set không null và chứa các Status hợp lệ. Nó không định nghĩa hợp đồng cho giá trị null.

### Đăng ký bean trong một profile riêng

Khi dùng Spring Boot, chỉ tạo đối tượng bằng `new` trong một lớp bình thường chưa làm endpoint sử dụng nó. Cần đăng ký bean.

`ConservativeAggregationConfiguration.java`:

~~~java
package com.example.aggregation;

import org.springframework.boot.actuate.health.StatusAggregator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("conservative")
public class ConservativeAggregationConfiguration {
    @Bean
    StatusAggregator healthStatusAggregator() {
        return new ConservativeStatusAggregator();
    }
}
~~~

Bật profile `conservative` để endpoint dùng triển khai này. Khi không bật profile, Spring Boot có thể tự cấu hình SimpleStatusAggregator theo properties nếu chưa có bean khác.

Sau khi đã cung cấp bean riêng, việc chỉnh `management.endpoint.health.status.order` không tự thay thuật toán trong bean đó. Mã trên cũng không đọc thuộc tính này. Không cấu hình một danh sách rồi kết luận chắc chắn nó đang điều khiển bean tự viết.

Cơ chế tự cấu hình chỉ tạo bộ tổng hợp khi thiếu bean phù hợp có thể đối chiếu trong [HealthEndpointConfiguration 3.3](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/HealthEndpointConfiguration.java).

## 9. Thực hành endpoint: quan sát thay đổi chính sách

Phần này bổ sung web server vào dự án ở phần 7. Giữ các lớp đã tạo, thêm dependency và xác định lớp khởi động để tách nó khỏi chương trình console:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

springBoot {
    mainClass = 'com.example.aggregation.AggregationApplication'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Các khai báo dependency được ghép vào block của dự án; không cần khai báo lại actuator lần thứ hai.

`AggregationApplication.java`:

~~~java
package com.example.aggregation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AggregationApplication {
    public static void main(String[] args) {
        SpringApplication.run(AggregationApplication.class, args);
    }
}
~~~

`DemoHealthConfiguration.java`:

~~~java
package com.example.aggregation;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class DemoHealthConfiguration {
    @Bean
    HealthIndicator primaryHealthIndicator() {
        return () -> Health.up()
            .withDetail("source", "simulated")
            .build();
    }

    @Bean
    HealthIndicator remoteHealthIndicator(
            @Value("${lab.remote-status:DEGRADED}") String remoteStatus) {
        return () -> Health.status(remoteStatus)
            .withDetail("source", "simulated")
            .build();
    }
}
~~~

Đây là hai phép kiểm tra mô phỏng, không kết nối ra hệ thống thật. Bean có hậu tố HealthIndicator nên ID tương ứng là `primary` và `remote`.

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
      show-components: always
      show-details: never
      probes:
        enabled: false
  health:
    defaults:
      enabled: false

lab:
  remote-status: DEGRADED
~~~

Tắt indicator tự cấu hình mặc định giúp bài thử chỉ dùng các contributor mô phỏng. Ví dụ không thêm Spring Security và chỉ lắng nghe loopback. Nếu dùng trong dự án có bảo mật, cần đáp ứng chính sách của dự án đó.

### 9.1. Chạy với bộ tổng hợp mặc định

~~~powershell
.\gradlew.bat bootRun
~~~

Ở terminal khác:

~~~powershell
curl.exe -i `
    -H "Accept: application/vnd.spring-boot.actuator.v3+json" `
    http://127.0.0.1:8080/actuator/health
~~~

Mã HTTP là 200; body có ý nghĩa tương đương:

~~~json
{
  "status": "UP",
  "components": {
    "primary": {
      "status": "UP"
    },
    "remote": {
      "status": "DEGRADED"
    }
  }
}
~~~

Đây không phải lỗi hiển thị. DEGRADED chưa có trong thứ tự mặc định, nên UP được chọn.

### 9.2. Cấu hình bộ tổng hợp nhận biết DEGRADED

Tạo `src/main/resources/application-ordered.yml`:

~~~yaml
management:
  endpoint:
    health:
      status:
        order:
          - down
          - out-of-service
          - degraded
          - unknown
          - up
~~~

Dừng lần chạy trước bằng Ctrl+C rồi chạy:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=ordered"
~~~

Kết luận root trở thành DEGRADED, nhưng HTTP vẫn là 200 vì chưa có mapping riêng. Hai component vẫn giữ trạng thái của chúng; đổi chính sách tổng hợp không tự viết lại kết quả indicator.

### 9.3. Bổ sung ánh xạ HTTP

Tạo `src/main/resources/application-mapped.yml`:

~~~yaml
management:
  endpoint:
    health:
      status:
        http-mapping:
          down: 503
          out-of-service: 503
          degraded: 503
~~~

Khởi động lại:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=ordered,mapped"
~~~

Root vẫn là DEGRADED; HTTP lúc này là 503. Đây là thay đổi ở lớp ánh xạ, không phải một lần kiểm tra mạng mới.

### 9.4. Thử một mã mà danh sách không biết

Khởi động lại với remote là MYSTERY:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=ordered,mapped --lab.remote-status=MYSTERY"
~~~

Root lại là UP, HTTP 200: danh sách ordered vẫn không biết MYSTERY, còn primary trả UP.

Đổi sang bean thận trọng:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=conservative,mapped --lab.remote-status=MYSTERY"
~~~

Root thành UNKNOWN vì bean không bỏ qua mã lạ. HTTP vẫn là 200 vì profile mapped chưa ánh xạ UNKNOWN. Muốn UNKNOWN trả 503 phải quyết định và khai báo thêm `unknown: 503`; không suy ra điều đó chỉ từ tên profile conservative.

Thứ tự khóa JSON không có ý nghĩa chính sách. Khi xác minh, so sánh status và HTTP riêng, không so nguyên chuỗi phản hồi.

## 10. Kiểm thử ma trận thay vì một nhánh UP

Tạo `src/test/java/com/example/aggregation/StatusAggregationTest.java`:

~~~java
package com.example.aggregation;

import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.boot.actuate.health.SimpleStatusAggregator;
import org.springframework.boot.actuate.health.Status;
import org.springframework.boot.actuate.health.StatusAggregator;

import static org.junit.jupiter.api.Assertions.assertEquals;

class StatusAggregationTest {
    private final StatusAggregator defaults = new SimpleStatusAggregator();
    private final StatusAggregator ordered = new SimpleStatusAggregator(
        "DOWN", "OUT_OF_SERVICE", "DEGRADED", "UNKNOWN", "UP"
    );
    private final StatusAggregator conservative =
        new ConservativeStatusAggregator();

    @ParameterizedTest
    @MethodSource("cases")
    void comparePolicies(Set<Status> input, String defaultCode,
                         String orderedCode, String conservativeCode) {
        assertEquals(defaultCode,
            defaults.getAggregateStatus(input).getCode(), "default");
        assertEquals(orderedCode,
            ordered.getAggregateStatus(input).getCode(), "ordered");
        assertEquals(conservativeCode,
            conservative.getAggregateStatus(input).getCode(), "conservative");
    }

    static Stream<Arguments> cases() {
        return Stream.of(
            Arguments.of(statuses(), "UNKNOWN", "UNKNOWN", "UNKNOWN"),
            Arguments.of(statuses("UP"), "UP", "UP", "UP"),
            Arguments.of(statuses("UP", "DOWN"), "DOWN", "DOWN", "DOWN"),
            Arguments.of(statuses("UP", "OUT_OF_SERVICE"),
                "OUT_OF_SERVICE", "OUT_OF_SERVICE", "OUT_OF_SERVICE"),
            Arguments.of(statuses("UP", "UNKNOWN"),
                "UP", "UNKNOWN", "UNKNOWN"),
            Arguments.of(statuses("UP", "DEGRADED"),
                "UP", "DEGRADED", "DEGRADED"),
            Arguments.of(statuses("DEGRADED"),
                "UNKNOWN", "DEGRADED", "DEGRADED"),
            Arguments.of(statuses("UP", "MYSTERY"),
                "UP", "UP", "UNKNOWN"),
            Arguments.of(statuses("MYSTERY"),
                "UNKNOWN", "UNKNOWN", "UNKNOWN"),
            Arguments.of(statuses("DOWN", "DEGRADED"),
                "DOWN", "DOWN", "DOWN"),
            Arguments.of(statuses("UP", "DEGRADED", "UNKNOWN"),
                "UP", "DEGRADED", "UNKNOWN")
        );
    }

    private static Set<Status> statuses(String... codes) {
        return Arrays.stream(codes)
            .map(Status::new)
            .collect(Collectors.toSet());
    }
}
~~~

Có 11 trường hợp đầu vào, mỗi trường hợp kiểm tra ba chính sách. Trường hợp cuối đặc biệt hữu ích: ordered chọn DEGRADED trước UNKNOWN, còn conservative chủ động chọn UNKNOWN trước DEGRADED.

### Kiểm tra thêm việc wiring và ánh xạ HTTP

Tạo `src/test/java/com/example/aggregation/AggregationHttpTest.java`:

~~~java
package com.example.aggregation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "lab.remote-status=DEGRADED",
    "management.endpoint.health.status.order=down,out-of-service,degraded,unknown,up",
    "management.endpoint.health.status.http-mapping.down=503",
    "management.endpoint.health.status.http-mapping.out-of-service=503",
    "management.endpoint.health.status.http-mapping.degraded=503"
})
@AutoConfigureMockMvc
class AggregationHttpTest {
    @Autowired MockMvc mvc;

    @Test
    void orderedStatusIsMappedToHttp() throws Exception {
        mvc.perform(get("/actuator/health"))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.status").value("DEGRADED"))
            .andExpect(jsonPath("$.components.primary.status").value("UP"))
            .andExpect(jsonPath("$.components.remote.status").value("DEGRADED"));
    }
}
~~~

Chạy:

~~~powershell
.\gradlew.bat test --tests "*StatusAggregationTest" --tests "*AggregationHttpTest"
~~~

Kiểm thử thuần kiểm tra thuật toán; kiểm thử MockMvc còn kiểm tra properties có được dùng để dựng aggregator và mapper của endpoint hay không. Chạy test với đúng dự án tối thiểu, không vô tình kích hoạt profile conservative từ cấu hình bên ngoài.

Sau khi dùng bean riêng, nên bổ sung kiểm thử tích hợp tương ứng để chứng minh endpoint thực sự dùng bean đó. Kiểm thử `new ConservativeStatusAggregator()` đạt không tự chứng minh việc đăng ký Spring đã đúng.

## 11. Phạm vi tổng hợp: cây và health group

### 11.1. Nút cha nhận kết quả của nút con

Trong cây contributor, một nhánh tổng hợp nhận trạng thái các con, rồi kết luận của nó lại đi lên nút cha. Aggregator ở cha không tự khôi phục mọi thông tin lá đã bị rút gọn.

Ví dụ, khi cùng dùng một chính sách ưu tiên:

~~~text
gốc
├── primary: UP
└── partners: DEGRADED
    ├── delivery: UP
    └── payment: DEGRADED
~~~

Nếu chính sách nhận biết DEGRADED và ưu tiên nó trước UP, partners và gốc đều có thể thành DEGRADED.

Với chính sách tùy chỉnh, cần kiểm thử cả cây nhiều tầng, không chỉ tập trạng thái phẳng. Những mã do bộ tổng hợp trả về phải tiếp tục có ý nghĩa khi được dùng làm đầu vào ở nút cha.

Framework lấy status của các kết quả con để tạo Set cho bước tổng hợp; xem [HealthEndpointSupport 3.3](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointSupport.java).

### 11.2. Group chọn đầu vào; aggregator chọn kết luận

Nếu không muốn lỗi của một dependency tùy chọn ảnh hưởng một góc nhìn phục vụ cụ thể, có thể thiết kế health group với danh sách thành viên thích hợp. Đó là việc chọn tập contributor, khác với đổi cách ưu tiên các Status.

Group mặc định kế thừa thiết lập tổng hợp và ánh xạ của system health, nhưng có thể có thiết lập riêng. Ví dụ minh họa nếu group tên `serving` thực sự cần chính sách khác:

~~~yaml
management:
  endpoint:
    health:
      group:
        serving:
          include: primary,remote
          status:
            order: down,out-of-service,degraded,unknown,up
            http-mapping:
              down: 503
              out-of-service: 503
              degraded: 503
~~~

Đoạn này là cấu hình bổ sung, không thuộc các profile chạy ở phần 9. Các ID được include phải tồn tại. Nếu cần bean riêng theo group, Spring Boot hỗ trợ qualifier theo tên group; không dùng `@Order` của Spring bean để biểu diễn độ nghiêm trọng của health status.

Không đổi chính sách toàn hệ thống chỉ để chữa kết quả của một group mà chưa xem xét các nơi còn sử dụng health. Liveness, readiness và một nhóm chẩn đoán có mục đích khác nhau; một quyết định có thể dẫn tới cảnh báo, ngừng nhận lưu lượng hoặc khởi động lại tùy hệ thống giám sát. Các quy tắc group nằm trong [tài liệu health groups 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.groups).

## 12. Những cách dùng dễ gây kết luận sai

| Cách làm | Vấn đề |
| --- | --- |
| Xem aggregator như lấy đa số | Set đầu vào không giữ số lượng của từng trạng thái |
| Giả định UNKNOWN luôn ưu tiên trước UP | Mặc định Boot 3.3 đặt UP trước UNKNOWN |
| Chỉ thêm mã tùy chỉnh ở indicator | Bộ tổng hợp có thể chưa nhận biết mã đó |
| Danh sách chỉ có DEGRADED và UP | Có thể làm DOWN bị bỏ khỏi các mã được nhận biết |
| Chỉ đặt HTTP mapping cho DEGRADED | Không thay đổi việc DEGRADED có được chọn làm root hay không |
| Chỉ đặt `degraded: 503` trong mapping tùy chỉnh | Không giữ tự động ánh xạ lỗi chuẩn |
| Chỉnh property rồi quên bean aggregator riêng | Bean có thể không đọc property ấy |
| Sắp xếp status theo tên chữ cái | Không phản ánh chính sách sức khỏe đã thống nhất |
| Chọn phần tử đầu tiên trong Set | Kết quả có thể phụ thuộc thứ tự không được bảo đảm |
| Gọi mạng hoặc sửa registry trong aggregator | Trộn việc kiểm tra với chính sách kết luận, tạo tác động phụ |
| Dùng details để báo lỗi nhưng giữ status UP | Aggregator chỉ nhận status, không tự hiểu trường details |
| Test thuật toán rồi coi wiring cũng đúng | Endpoint có thể đang dùng cấu hình hoặc bean khác |

Khi kết quả bất ngờ, kiểm tra theo chuỗi: **tập contributor thuộc phạm vi → status thật từng nút → aggregator đang được dùng → danh sách hoặc thuật toán của nó → mapper HTTP**.

Nếu không nhận được phản hồi do timeout/kết nối lỗi, đó không phải là aggregator đã trả UNKNOWN. Cần phân biệt lỗi gọi endpoint với một phản hồi health hợp lệ.

## 13. Tự kiểm tra

1. Vì sao UP cùng DEGRADED có thể kết luận UP ở mặc định nhưng thành DEGRADED sau khi cấu hình order?
2. Vì sao hai tập gồm một UP/một DOWN và nhiều UP/một DOWN có thể không phân biệt được qua hợp đồng Set?
3. Chỉ muốn thêm DEGRADED vào chính sách, vì sao vẫn phải ghi rõ DOWN và OUT_OF_SERVICE?
4. Root đã là DEGRADED nhưng HTTP vẫn 200: lớp nào cần xem xét?
5. UNKNOWN do mã lạ bị bỏ hết khác gì một indicator chủ động trả UNKNOWN?
6. Nếu bean tự viết không đọc properties, việc đổi status.order có tác dụng gì lên thuật toán của bean?
7. Khi lỗi đến từ dependency tùy chọn, nên xem xét group membership thế nào trước khi đổi chính sách tổng hợp chung?

Bạn hiểu đúng StatusAggregator khi có thể viết trước bảng kết quả mong muốn, chọn đủ đầu vào cho từng phạm vi và kiểm chứng riêng **thuật toán tổng hợp, việc đăng ký sử dụng và ánh xạ HTTP**.

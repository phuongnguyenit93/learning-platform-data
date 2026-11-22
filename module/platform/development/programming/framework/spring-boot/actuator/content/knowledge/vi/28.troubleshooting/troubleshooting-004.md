# Xử lý health DOWN, UNKNOWN và kết quả không có chi tiết

## 1. Một phản hồi health có ba lớp thông tin

Khi `/actuator/health` trả `DOWN`, chưa thể kết luận tiến trình Java đã chết. Khi trả HTTP 200, cũng chưa thể kết luận mọi chức năng nghiệp vụ đều hoạt động. Cần đọc đồng thời trạng thái sức khỏe, mã HTTP và phạm vi dữ liệu được công bố.

| Lớp | Ví dụ | Câu hỏi cần trả lời |
| --- | --- | --- |
| Trạng thái sức khỏe (health status) | `UP`, `DOWN`, `OUT_OF_SERVICE`, `UNKNOWN` | Các phép kiểm tra đang đánh giá hệ thống thế nào? |
| Mã HTTP | 200, 503 | Trạng thái sức khỏe đã được ánh xạ ra giao thức như thế nào? |
| Nội dung hiển thị | `components`, `details` hoặc chỉ `status` | Người gọi được xem đến mức nào và indicator có tạo chi tiết không? |

Mô hình xử lý rút gọn:

```text
HealthIndicator / cây HealthContributor
  -> chọn các thành phần thuộc health group đang gọi
  -> StatusAggregator tổng hợp trạng thái
  -> HttpCodeStatusMapper ánh xạ trạng thái sang mã HTTP
  -> áp dụng chính sách hiển thị components và details
  -> trả phản hồi cho người gọi
```

Đây là các trách nhiệm logic, không phải cam kết thứ tự thực thi từng câu lệnh. `HealthEndpointGroup` có bộ tổng hợp, bộ ánh xạ và chính sách hiển thị riêng. Vì vậy root health, readiness và một nhóm tự định nghĩa có thể cho kết quả khác nhau mà vẫn đúng cấu hình. [Hợp đồng HealthEndpointGroup](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthEndpointGroup.html).

Bài này tập trung vào chẩn đoán với Spring Boot 3.3.13, Java 21 và Spring MVC/Servlet. Phần trạng thái và nhóm cũng có ích khi dùng WebFlux, nhưng cấu hình bảo mật Servlet trong ví dụ không dùng nguyên xi cho WebFlux.

## 2. Diễn giải DOWN và UNKNOWN đúng phạm vi

### 2.1. DOWN là kết quả đánh giá, không phải tên một nguyên nhân

`DOWN` cho biết ít nhất một điều kiện đang bị đánh giá là không khỏe theo quy tắc của indicator và bộ tổng hợp hiện tại. Trong hệ thống thực, điều kiện đó có thể là kết nối cơ sở dữ liệu thất bại, thiếu dung lượng đĩa, truy cập dịch vụ phụ thuộc bị từ chối hoặc một phép kiểm tra tự viết không đạt.

Cần đi xuống thành phần gây lỗi thay vì sửa ngay root status:

```json
{
  "status": "DOWN",
  "components": {
    "catalog": {
      "status": "DOWN",
      "details": {
        "dependency": "catalog-stub",
        "reason": "simulated_unavailable"
      }
    }
  }
}
```

Đây là hình dạng dữ liệu minh họa cho thí nghiệm phía dưới. Không suy ra tên dịch vụ, địa chỉ kết nối hoặc lỗi thực tế từ một mẫu JSON. Trong dữ liệu Actuator V3, `status` ở root là kết quả chung; `components.<id>.status` là trạng thái thành phần và `components.<id>.details` là chi tiết của thành phần đó. Không phải mọi chi tiết đều nằm ở `details` ngay dưới root. [Cấu trúc phản hồi health V3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

### 2.2. UNKNOWN nghĩa là chưa có kết luận được biểu diễn theo quy tắc hiện tại

`UNKNOWN` không đồng nghĩa `DOWN`, cũng không phải một cách viết khác của `UP`. Hãy kiểm tra hai tầng:

- Indicator có chủ động trả `UNKNOWN` vì chưa có mẫu đo, chưa sẵn sàng đánh giá hoặc chưa đặt trạng thái không?
- Các trạng thái con có được bộ tổng hợp nhận diện không, đặc biệt khi có mã tự định nghĩa như `DEGRADED`?

Với `SimpleStatusAggregator` mặc định của đúng phiên bản 3.3.13, thứ tự ưu tiên là `DOWN`, `OUT_OF_SERVICE`, `UP`, `UNKNOWN`; trạng thái đứng trước trong danh sách được ưu tiên. Bộ tổng hợp bỏ qua mã không có trong thứ tự rồi chọn trạng thái được nhận diện ưu tiên cao nhất; nếu không có mã được nhận diện thì trả `UNKNOWN`.

| Trạng thái con đầu vào | Kết quả tổng hợp mặc định |
| --- | --- |
| `UP` và `DOWN` | `DOWN` |
| `UP` và `UNKNOWN` | `UP` |
| Chỉ `UNKNOWN` | `UNKNOWN` |
| Chỉ `DEGRADED`, chưa khai báo thứ tự | `UNKNOWN` |
| `UP` và `DEGRADED`, chưa khai báo thứ tự | `UP` |

Điểm cần lưu ý: đây không phải biểu quyết theo số lượng indicator; nhiều thành phần `UP` không thắng một thành phần `DOWN`. Cũng không được đọc ví dụ cấu hình một thứ tự tùy biến trong tài liệu rồi coi đó là thứ tự mặc định. [Mã nguồn SimpleStatusAggregator 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.java).

Không suy luận 'không thấy components nên chắc chắn không có indicator và root phải UNKNOWN'. Việc ẩn dữ liệu là chuyện khác với đăng ký indicator. Ngoài ra, endpoint root hoàn toàn không có kết quả đóng góp còn có nhánh trả `UP` mặc định trong phiên bản này; không nên đánh đồng trường hợp đó với tập trạng thái con không được nhận diện. [Xử lý kết quả root trong HealthEndpointWebExtension](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointWebExtension.java).

### 2.3. Mã HTTP và health status là hai giá trị khác nhau

Với ánh xạ mặc định của Spring Boot 3.3:

| Health status | HTTP mặc định | Cách đọc |
| --- | --- | --- |
| `UP` | 200 | Các phép kiểm tra tham gia đã cho kết quả này |
| `DOWN` | 503 | Bộ tổng hợp đánh giá không khỏe |
| `OUT_OF_SERVICE` | 503 | Đang ngoài khả năng/phạm vi phục vụ theo phép kiểm tra |
| `UNKNOWN` | 200 | Chưa có kết luận sức khỏe rõ ràng; 200 không biến nó thành UP |

`HttpCodeStatusMapper` làm nhiệm vụ ánh xạ trạng thái sức khỏe sang mã HTTP. Chính sách ánh xạ có thể được thay thế, nên cần đọc cấu hình có hiệu lực và cả JSON khi điều tra. [API SimpleHttpCodeStatusMapper](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleHttpCodeStatusMapper.html).

HTTP 503 kèm JSON health `DOWN` cho thấy đã nhận được một đánh giá từ endpoint, khác với 401/403 do lớp bảo mật từ chối hoặc 503 do proxy tự sinh khi không kết nối được ứng dụng. Hãy kiểm tra nguồn phản hồi; đừng chỉ đọc số 503 trong bảng giám sát.

## 3. Vì sao không có components hoặc details?

Cần phân biệt tên thành phần, dữ liệu chi tiết và quyền truy cập URL:

| Cấu hình | Điều được kiểm soát |
| --- | --- |
| `management.endpoint.health.show-components` | Có công bố cây thành phần trong phản hồi không |
| `management.endpoint.health.show-details` | Có công bố dữ liệu chi tiết của indicator không |
| `management.endpoint.health.roles` | Vai trò được xem khi chính sách dùng `when-authorized` |
| Rule trong `SecurityFilterChain` | Người gọi có được truy cập URL health hay không |

Hai chính sách hiển thị nhận `never`, `when-authorized`, `always`. `show-details` mặc định là `never`; khi không đặt riêng `show-components`, hành vi hiển thị thành phần theo chính sách chi tiết. Với `when-authorized`, nếu có danh sách roles thì người gọi phải có ít nhất một vai trò trong danh sách; nếu không đặt roles, người đã xác thực được xem. [Chính sách hiển thị health của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health).

Những tình huống không nhất thiết là lỗi:

- Chỉ thấy `{"status":"DOWN"}`: vẫn có thể đã chạy đầy đủ các phép kiểm tra, nhưng người gọi không được xem cây và chi tiết.
- Thấy `components.catalog.status` nhưng không có `details`: có thể đang cho xem thành phần nhưng ẩn chi tiết.
- Có quyền xem chi tiết nhưng một indicator chỉ trả `Health.up().build()`: indicator đó không tạo dữ liệu bổ sung để hiển thị.
- Phản hồi root không có `details` nhưng các thành phần con có: cấu trúc dữ liệu đang đúng, cần đọc đúng vị trí.

`HealthIndicator.getHealth(includeDetails)` cho phép giữ hoặc bỏ phần chi tiết mà vẫn trả kết quả health. Vì vậy bật hiển thị không sửa một phép kiểm tra thất bại; ẩn chi tiết cũng không làm phép kiểm tra ngừng chạy. [Hợp đồng HealthIndicator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthIndicator.html).

Cấu hình có kiểm soát thường dùng cho điều tra:

```properties
management.endpoint.health.show-components=when-authorized
management.endpoint.health.show-details=when-authorized
management.endpoint.health.roles=OPS
```

`roles=OPS` ở đây điều khiển việc xem dữ liệu, không tự áp đặt rule bảo vệ URL. Nếu URL cho phép truy cập công khai, người chưa đăng nhập vẫn có thể nhận trạng thái tổng hợp nhưng không có chi tiết. Ngược lại, đặt `always` không vượt qua một rule bảo mật đang chặn URL.

Đừng công khai toàn bộ chi tiết chỉ để xác định nguyên nhân. Dữ liệu indicator có thể chứa tên máy chủ, đường dẫn, tên cơ sở dữ liệu hoặc thông báo exception. Trong điều tra, dùng tài khoản có quyền và chỉ thu thập dữ liệu cần thiết.

## 4. Chẩn đoán DOWN: tìm phép kiểm tra thất bại rồi sửa điều kiện

### Bước 1: Xác định đúng endpoint và thời điểm

Ghi lại URL, cổng quản trị, profile, phiên bản ứng dụng, instance/pod và thời điểm lấy mẫu. Root `/actuator/health`, `/actuator/health/readiness` và `/actuator/health/liveness` có thể dùng tập thành phần khác nhau.

Nếu có proxy hoặc cân bằng tải, hai lần GET liên tiếp có thể tới hai instance khác nhau. Khi điều tra một lỗi chập chờn, cần gắn phản hồi với đúng instance và đối chiếu log cùng thời điểm.

### Bước 2: Lấy trạng thái thành phần bằng quyền phù hợp

Đọc health bằng tài khoản được xem chi tiết. Tìm thành phần `DOWN`, rồi xem `reason`, `error` hoặc các trường mà indicator thực sự cung cấp. Với contributor tổng hợp, tiếp tục đi xuống các cấp con.

Có thể truy vấn một thành phần theo đường dẫn `/actuator/health/<component-id>` khi thành phần tồn tại và chính sách cho phép. Không đoán ID từ tên class Java: ID được hình thành từ tên bean theo quy tắc đăng ký. Khi `show-components` không cho phép, đường dẫn thành phần có thể trả 404 dù root vẫn trả trạng thái. [Kiểm tra phạm vi thành phần trong HealthEndpointSupport](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointSupport.java).

### Bước 3: Kiểm tra phụ thuộc từ cùng môi trường chạy ứng dụng

| Thành phần đang DOWN | Điều cần xác minh |
| --- | --- |
| Cơ sở dữ liệu | DNS/host/port, đường mạng, TLS, credential, giới hạn kết nối, khả năng mượn connection và phép kiểm tra cụ thể |
| Dung lượng đĩa | Phân vùng/path thực tế, dung lượng còn lại, ngưỡng và volume được mount trong container |
| Cache hoặc message broker | Endpoint và xác thực có hiệu lực, ACL, TLS, kết nối và tài nguyên mà phép kiểm tra yêu cầu |
| Indicator tự viết | Quy tắc trả trạng thái, dữ liệu đầu vào, timeout và exception của chính phép kiểm tra |

Việc máy cá nhân kết nối được không chứng minh container kết nối được. Cũng không thay mật khẩu, tăng pool hay đổi timeout chỉ vì thấy `DOWN`; mỗi thay đổi cần gắn với bằng chứng cụ thể.

### Bước 4: Phân biệt lỗi phụ thuộc và lỗi của chính phép kiểm tra

Một indicator có thể kiểm tra sai địa chỉ, dùng credential cũ, yêu cầu quyền quá rộng hoặc coi một tình trạng chấp nhận được là lỗi nghiêm trọng. Khi đó cần sửa phép kiểm tra hoặc cấu hình của nó, thay vì sửa một dịch vụ vốn đang hoạt động đúng.

Nếu dùng `AbstractHealthIndicator`, exception phát sinh từ `doHealthCheck` được chuyển thành trạng thái `DOWN` theo hợp đồng của lớp này. Không khái quát rằng mọi exception từ mọi triển khai `HealthIndicator` đều được xử lý giống nhau. [API AbstractHealthIndicator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/AbstractHealthIndicator.html).

Đừng bọc mọi exception rồi trả `UP` để biểu đồ xanh trở lại. Cần quyết định rõ điều kiện nào làm hệ thống không phục vụ được, điều kiện nào chỉ là suy giảm có thể xử lý bằng cơ chế dự phòng.

### Bước 5: Kiểm tra thời gian thực hiện

Nếu endpoint phản hồi chậm hoặc bị client timeout, xem thời gian kết nối, đọc và chờ tài nguyên trong từng indicator. Log cảnh báo indicator chạy chậm chỉ là tín hiệu chẩn đoán; ngưỡng log không tự đặt deadline hay hủy lời gọi mạng. Hãy đặt timeout ở thư viện truy cập phụ thuộc và giữ phép kiểm tra nhẹ, không có thao tác ghi nghiệp vụ.

### Bước 6: Kiểm chứng sau sửa

Đọc lại cùng nhóm, cùng instance và cùng tài khoản. Xác nhận thành phần gây lỗi phục hồi rồi mới kiểm tra trạng thái tổng hợp và mã HTTP. Đối chiếu thêm một phép thử nghiệp vụ đại diện: health chỉ biết những điều mà các phép kiểm tra đã quan sát.

## 5. Chẩn đoán UNKNOWN: tìm nguồn thiếu kết luận

Thực hiện theo thứ tự sau:

1. Mở cây thành phần bằng quyền phù hợp; xác định `UNKNOWN` nằm ở một indicator hay chỉ ở kết quả tổng hợp.
2. Nếu indicator trả `UNKNOWN`, đọc logic đặt trạng thái và dữ liệu cần có trước khi đánh giá. Trạng thái này có chủ ý hay là do quên đặt `UP`/`DOWN`?
3. Nếu các thành phần có mã tự định nghĩa, kiểm tra `management.endpoint.health.status.order` và mọi bean `StatusAggregator` đang được áp dụng.
4. Kiểm tra tập thành viên của nhóm đang gọi, profile và điều kiện đăng ký bean. Đừng suy từ cấu hình dự kiến rằng một indicator chắc chắn đã được đăng ký.
5. Xem chính sách giám sát xử lý `UNKNOWN` thế nào. Đừng coi HTTP 200 của UNKNOWN là bằng chứng đã có kết luận tích cực.

Nếu nghiệp vụ cần coi `UNKNOWN` nghiêm trọng hơn `UP`, phải xác định và kiểm thử chính sách đó rõ ràng. Thay thứ tự tổng hợp tác động tới toàn bộ các trạng thái tham gia, không chỉ đổi một nhãn trên giao diện.

Với trạng thái tự định nghĩa, cần giải quyết hai việc độc lập: có nhận diện mã trong phép tổng hợp hay không, và mã đã tổng hợp được ánh xạ sang HTTP thế nào. Chỉ thêm `http-mapping.degraded=503` không làm bộ tổng hợp tự nhận diện `DEGRADED`.

Ví dụ một chính sách có chủ ý coi UNKNOWN nghiêm trọng hơn UP:

```properties
management.endpoint.health.status.order=degraded,down,out-of-service,unknown,up
management.endpoint.health.status.http-mapping.degraded=503
management.endpoint.health.status.http-mapping.down=503
management.endpoint.health.status.http-mapping.out-of-service=503
management.endpoint.health.status.http-mapping.unknown=503
```

Đây là lựa chọn chính sách minh họa, không phải cấu hình mặc định. Khi khai báo ánh xạ HTTP tùy biến bằng cấu hình này, phải khai báo lại `DOWN` và `OUT_OF_SERVICE` nếu muốn giữ ánh xạ 503 mặc định. Việc chỉ đổi `DOWN` sang HTTP 200 không khắc phục điều kiện khiến nó DOWN.

## 6. Thực hành độc lập: tái hiện trạng thái và quyền xem chi tiết

### 6.1. Phạm vi thí nghiệm

Ví dụ có đúng một indicator tùy biến tên `catalog`. Nó mô phỏng kết quả, không kết nối mạng tới một dịch vụ thật. Ta tắt các indicator tự động trong riêng dự án này để kết quả `UNKNOWN` không bị một indicator `UP` khác làm thay đổi khi tổng hợp.

Dùng Java 21, Maven 3.6.3 trở lên và Python 3. Maven cần truy cập kho dependency nếu chưa có bộ nhớ đệm. Cấu trúc dự án:

```text
health-diagnosis-lab/
├── pom.xml
├── verify.py
└── src/main/
    ├── java/example/health/HealthDiagnosisLab.java
    └── resources/application.properties
```

### 6.2. Cấu hình build và ứng dụng

Tệp pom.xml:

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
    <artifactId>health-diagnosis-lab</artifactId>
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
            <artifactId>spring-boot-starter-security</artifactId>
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

Tệp src/main/resources/application.properties:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health
management.health.defaults.enabled=false
management.endpoint.health.show-components=when-authorized
management.endpoint.health.show-details=when-authorized
management.endpoint.health.roles=OPS
lab.mode=DOWN
```

Tệp src/main/java/example/health/HealthDiagnosisLab.java:

```java
package example.health;

import jakarta.servlet.DispatcherType;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.AbstractHealthIndicator;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
public class HealthDiagnosisLab {
    public enum Mode { UP, DOWN, UNKNOWN, DEGRADED, THROW }

    public static void main(String[] args) {
        SpringApplication.run(HealthDiagnosisLab.class, args);
    }

    @Bean
    HealthIndicator catalogHealthIndicator(@Value("${lab.mode:DOWN}") Mode mode) {
        return new AbstractHealthIndicator() {
            @Override
            protected void doHealthCheck(Health.Builder builder) {
                builder.withDetail("dependency", "catalog-stub");
                switch (mode) {
                    case UP -> builder.up().withDetail("reason", "simulated_ok");
                    case DOWN -> builder.down()
                        .withDetail("reason", "simulated_unavailable");
                    case UNKNOWN -> builder.unknown()
                        .withDetail("reason", "not_evaluated");
                    case DEGRADED -> builder.status("DEGRADED")
                        .withDetail("reason", "partial_capacity");
                    case THROW -> throw new IllegalStateException("simulated probe failure");
                }
            }
        };
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("viewer").password("{noop}viewer-pass")
                .roles("VIEWER").build(),
            User.withUsername("ops").password("{noop}ops-pass")
                .roles("OPS").build()
        );
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
            .requestMatchers(EndpointRequest.to("health")).permitAll()
            .anyRequest().denyAll()
        );
        http.httpBasic(withDefaults());
        return http.build();
    }
}
```

`catalogHealthIndicator` là tên bean, còn ID thành phần hiển thị là `catalog` sau khi bỏ hậu tố `HealthIndicator`. Tài khoản viewer có thể gọi URL nhưng không có vai trò OPS để xem chi tiết. Tài khoản ops có vai trò đó. Cho phép `DispatcherType.ERROR` nhằm tránh chặn lần dựng phản hồi lỗi; không cấp quyền cho mọi yêu cầu trực tiếp tới `/error`.

Mật khẩu cố định và `{noop}` chỉ dành cho thí nghiệm loopback. Khi dùng trong môi trường thực, cần cơ chế quản lý danh tính phù hợp và HTTPS cho HTTP Basic. Không đưa nguyên cấu hình tài khoản minh họa vào dịch vụ công khai.

Build tại thư mục gốc của dự án:

```shell
mvn package
```

Đây là dự án có dependency Spring Boot nên không thể biên dịch đầy đủ bằng cách chỉ gọi `javac` trên tệp Java. Sau khi build xong, khởi động:

```shell
java -jar target/health-diagnosis-lab-1.0.0.jar
```

Giữ ứng dụng chạy, mở terminal thứ hai tại cùng thư mục. Đảm bảo cổng 8080 không đang thuộc về một ứng dụng khác.

### 6.3. Script kiểm tra status, HTTP và khả năng xem dữ liệu

Tệp verify.py dùng thư viện chuẩn Python. Các tham số lần lượt là trạng thái root mong đợi, mã HTTP mong đợi và trạng thái thành phần catalog mong đợi:

```python
import base64
import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

URL = "http://127.0.0.1:8080/actuator/health"


def read_health(credentials=None):
    headers = {"Accept": "application/json"}
    if credentials is not None:
        encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
        headers["Authorization"] = "Basic " + encoded
    request = Request(URL, headers=headers, method="GET")
    try:
        response = urlopen(request, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        return response.code, json.loads(response.read())


def main():
    if len(sys.argv) != 4:
        raise SystemExit("Usage: python verify.py ROOT_STATUS HTTP_CODE COMPONENT_STATUS")
    root_status, http_code, component_status = sys.argv[1:]
    http_code = int(http_code)
    cases = [
        ("anonymous", None, False),
        ("viewer", "viewer:viewer-pass", False),
        ("ops", "ops:ops-pass", True),
    ]
    for label, credentials, visible in cases:
        code, body = read_health(credentials)
        assert code == http_code, (label, code, body)
        assert body["status"] == root_status, (label, body)
        assert ("components" in body) == visible, (label, body)
        visibility = "visible" if visible else "hidden"
        print(f"{label}: HTTP={code}, status={body['status']}, components={visibility}")
        if visible:
            component = body["components"]["catalog"]
            assert component["status"] == component_status, component
            assert component["details"]["dependency"] == "catalog-stub", component
            print(f"catalog: status={component['status']}, dependency=catalog-stub")


if __name__ == "__main__":
    main()
```

Với cấu hình mặc định của dự án, chạy:

```shell
python verify.py DOWN 503 DOWN
```

Stdout chính xác:

```text
anonymous: HTTP=503, status=DOWN, components=hidden
viewer: HTTP=503, status=DOWN, components=hidden
ops: HTTP=503, status=DOWN, components=visible
catalog: status=DOWN, dependency=catalog-stub
```

Cùng trạng thái và cùng mã HTTP nhưng ba người gọi nhìn thấy lượng dữ liệu khác nhau. Việc bổ sung tài khoản OPS chỉ giúp quan sát nguyên nhân; nó không làm health chuyển sang UP.

Có thể xem phản hồi thô bằng các lệnh sau. Dùng `curl.exe` trên Windows nếu tên `curl` đang trỏ tới lệnh khác:

```shell
curl -i -H "Accept: application/json" http://127.0.0.1:8080/actuator/health
curl -i -u ops:ops-pass -H "Accept: application/json" http://127.0.0.1:8080/actuator/health
```

Không thêm `-f` rồi bỏ qua phần lỗi khi đang cần đọc body 503. Phản hồi health không đạt vẫn chứa bằng chứng hữu ích.

### 6.4. Tái hiện UNKNOWN và phục hồi UP

Dừng tiến trình hiện tại bằng Ctrl+C trước mỗi lần khởi động lại. Chạy lần lượt từng chế độ và lệnh kiểm chứng tương ứng ở terminal thứ hai:

| Chế độ | Lệnh khởi động | Lệnh kiểm chứng | Kết quả quan trọng |
| --- | --- | --- | --- |
| Chưa đánh giá | `java -jar target/health-diagnosis-lab-1.0.0.jar --lab.mode=UNKNOWN` | `python verify.py UNKNOWN 200 UNKNOWN` | Root UNKNOWN vẫn đi với HTTP 200 mặc định |
| Đánh giá tốt | `java -jar target/health-diagnosis-lab-1.0.0.jar --lab.mode=UP` | `python verify.py UP 200 UP` | Status và HTTP đều phản ánh kết quả mong đợi |
| Mã chưa được nhận diện | `java -jar target/health-diagnosis-lab-1.0.0.jar --lab.mode=DEGRADED` | `python verify.py UNKNOWN 200 DEGRADED` | Thành phần DEGRADED nhưng root UNKNOWN |
| Exception trong phép kiểm tra | `java -jar target/health-diagnosis-lab-1.0.0.jar --lab.mode=THROW` | `python verify.py DOWN 503 DOWN` | AbstractHealthIndicator chuyển exception thành DOWN |

Ở chế độ THROW, log máy chủ có cảnh báo và exception mô phỏng; đó không phải stdout của script verify.py. Khi được phép xem chi tiết, dữ liệu lỗi của indicator có thể xuất hiện trong phản hồi.

### 6.5. Nhận diện mã tự định nghĩa và kiểm thử ánh xạ

Chạy ứng dụng với DEGRADED và khai báo rõ thứ tự cùng ánh xạ HTTP. Lệnh sau viết trên một dòng để dùng được trong nhiều terminal:

```shell
java -jar target/health-diagnosis-lab-1.0.0.jar --lab.mode=DEGRADED --management.endpoint.health.status.order=degraded,down,out-of-service,up,unknown --management.endpoint.health.status.http-mapping.degraded=503 --management.endpoint.health.status.http-mapping.down=503 --management.endpoint.health.status.http-mapping.out-of-service=503
```

Kiểm chứng:

```shell
python verify.py DEGRADED 503 DEGRADED
```

Lần này root là DEGRADED và HTTP là 503. So sánh với chế độ DEGRADED ở bảng trước sẽ thấy khác biệt giữa dữ liệu indicator, quy tắc tổng hợp và cách ánh xạ HTTP. Thứ tự trong lệnh này chỉ thêm DEGRADED ở đầu, vẫn giữ UP trước UNKNOWN; không trộn với chính sách UNKNOWN nghiêm trọng hơn UP ở phần 5.

### 6.6. Hiện thành phần nhưng ẩn chi tiết

Dừng tiến trình trước, rồi chạy:

```shell
java -jar target/health-diagnosis-lab-1.0.0.jar --management.endpoint.health.show-components=always --management.endpoint.health.show-details=never
```

Lúc này cả người chưa đăng nhập lẫn OPS đều có thể thấy thành phần catalog và trạng thái DOWN, nhưng không thấy trường details của catalog. Quan sát bằng curl; không dùng nguyên script kiểm chứng phần 6.3 vì script đó đang kiểm tra chính sách `when-authorized` ban đầu.

Nếu đổi ngược lại thành `show-details=always` trong một URL công khai, cần đánh giá dữ liệu sẽ bị công bố. Không dùng thay đổi quyền hiển thị làm biện pháp khắc phục health DOWN.

## 7. Khi root health và probe đưa ra kết quả khác nhau

Một nhóm health là tập phép kiểm tra được chọn cho một mục đích. Root có thể DOWN vì catalog, trong khi readiness không bao gồm catalog nên vẫn UP. Điều cần điều tra là tập thành viên và quyết định vận hành mong muốn, không chỉ hai chuỗi trạng thái khác nhau.

Với probe, phân biệt:

- Liveness đánh giá khả năng tiếp tục sống của ứng dụng. Một phụ thuộc ngoài bị lỗi thường không được giải quyết bằng cách khởi động lại hàng loạt instance ứng dụng.
- Readiness phục vụ quyết định có chuyển lưu lượng vào instance hay không. Chỉ đưa một phụ thuộc vào nhóm này khi sự cố của nó thật sự khiến instance không nên nhận công việc.
- Việc một dependency có phương án dự phòng hay được dùng chung bởi mọi instance ảnh hưởng quyết định đưa nó vào readiness.

Không thêm mọi dependency ngoài vào liveness, và không loại indicator khỏi root/readiness chỉ để tránh báo động. Mỗi thay đổi tập thành viên phải có lý do và phép thử khi dependency thất bại.

Kiểm tra thêm ba điểm thực tế:

1. Nhóm probe đã được bật trong môi trường đang chạy chưa? Không suy từ môi trường triển khai dự kiến.
2. Cấu hình nhóm có ghi đè quyền xem, thứ tự hoặc ánh xạ HTTP so với root không?
3. Probe đang đi vào đúng hạ tầng web của ứng dụng chưa? Cổng management riêng trả tốt không chứng minh cổng nghiệp vụ còn nhận kết nối.

Nếu dự án dùng cổng management riêng, có thể thiết kế đường probe bổ sung trên cổng chính và kiểm thử quyền truy cập của nó. Không thay đổi cổng hoặc rule bảo mật trong lúc điều tra mà không theo dõi tác động tới hệ thống gọi probe.

## 8. Những cách sửa tạo tín hiệu sai

| Cách làm | Vì sao gây sai lệch | Cách xử lý có cơ sở |
| --- | --- | --- |
| Tắt indicator đang DOWN ngay lập tức | Mất phép đo nhưng điều kiện lỗi có thể còn nguyên | Xác định phép kiểm tra có phản ánh yêu cầu phục vụ không; sửa nguyên nhân hoặc thay đổi phạm vi có chủ ý |
| Luôn trả UP trong catch | Che cả lỗi thật và lỗi của phép kiểm tra | Phân loại lỗi và quy tắc sức khỏe rõ ràng |
| Đổi mọi status sang HTTP 200 | Bộ giám sát chỉ xét HTTP có thể báo tốt sai | Thống nhất hợp đồng HTTP và health status với nơi tiêu thụ |
| Bật always để 'sửa' DOWN | Chỉ thay lượng dữ liệu lộ ra | Dùng quyền xem phù hợp rồi xử lý điều kiện gây lỗi |
| Đặt slow-indicator-threshold thấp rồi coi đó là timeout | Ngưỡng log không hủy phép kiểm tra | Đặt timeout thật ở lời gọi và giới hạn chi phí kiểm tra |
| Chỉ nhìn root UP | Có thể bỏ sót mã tự định nghĩa bị bỏ qua, UNKNOWN con hoặc nghiệp vụ chưa được đo | Kiểm tra phạm vi quan sát và trạng thái thành phần cần thiết |
| So hai response từ hai instance | Có thể nhầm lỗi phân tán với lỗi cấu hình hiển thị | Gắn bằng chứng với instance, nhóm, thời điểm và danh tính người gọi |

## 9. Bài tập kiểm tra cách suy luận

1. HTTP 200 nhưng JSON là UNKNOWN: đã đủ để đánh dấu nghiệp vụ hoạt động tốt chưa?
2. Có một thành phần UP và một thành phần UNKNOWN: root mặc định của 3.3.13 là gì? Nếu muốn kết quả khác thì sửa tầng nào?
3. Chỉ có thành phần DEGRADED nhưng root UNKNOWN: thêm mỗi http-mapping.degraded=503 có đủ không?
4. Anonymous và OPS đều thấy DOWN nhưng chỉ OPS thấy details: đây có nhất thiết là lỗi xác thực hay không?
5. show-details=always mà một indicator vẫn không có details: cần kiểm tra điều gì trong mã indicator?
6. Cơ sở dữ liệu lỗi làm root DOWN nhưng readiness UP: cần xem tập thành viên hay đổi mọi HTTP status thành 200?

Hướng đối chiếu: câu 1 chưa đủ bằng chứng; câu 2 root là UP và muốn thay chính sách cần chỉnh bộ tổng hợp/thứ tự; câu 3 phải nhận diện DEGRADED trong tổng hợp rồi mới ánh xạ kết quả; câu 4 có thể đúng chính sách hiển thị; câu 5 kiểm tra indicator có tạo chi tiết và có cấu hình nhóm ghi đè không; câu 6 xác minh tập thành viên cùng mục đích readiness.

Một kết quả chẩn đoán có giá trị cần nêu được thành phần nào tạo trạng thái, quy tắc nào tổng hợp nó, ánh xạ HTTP nào đang áp dụng, người gọi được xem gì và bằng chứng nào cho thấy điều kiện lỗi đã được khắc phục.

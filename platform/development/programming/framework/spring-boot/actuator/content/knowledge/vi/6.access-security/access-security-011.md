# Bảo vệ heapdump, logfile, env và các endpoint có khả năng thay đổi trạng thái

## 1. Actuator là một mặt phẳng quản trị

Actuator cung cấp khả năng quan sát và điều khiển ứng dụng đang chạy. Những khả năng hữu ích cho người vận hành cũng có thể trở thành đường lấy dữ liệu hoặc gây gián đoạn nếu cấp quyền quá rộng.

Hai nhóm rủi ro cần phân biệt:

- **Lộ thông tin:** tải bộ nhớ JVM, đọc log hoặc xem cấu hình.
- **Thay đổi trạng thái:** đổi mức log, xóa dữ liệu cache, chấm dứt phiên hoặc dừng ứng dụng.

Một yêu cầu GET có thể không sửa dữ liệu nghiệp vụ nhưng vẫn rất nhạy cảm. Ví dụ, người có quyền tải heapdump có thể nhận nhiều dữ liệu trong bộ nhớ hơn người chỉ được gọi API nghiệp vụ. Bảo vệ Actuator vì thế không thể dừng ở quy tắc “GET cho mọi người, POST dành cho quản trị viên”.

Bài này dùng **Spring Boot 3.3.x, Spring Security 6.3.x, Java 21, Servlet/Spring MVC**. Phần thực hành giả định Actuator và ứng dụng dùng chung cổng, tiền tố `/actuator`, không có proxy thay đổi đường dẫn. Đây là ví dụ cho dự án thử độc lập, không phải cấu hình áp dụng nguyên xi vào mọi ứng dụng.

## 2. Hiểu đúng rủi ro của từng endpoint

### 2.1. Heapdump: quyền xem ảnh chụp bộ nhớ

`GET /actuator/heapdump` tạo và trả về heap dump của JVM. Định dạng phụ thuộc JVM; HotSpot thường dùng HPROF. Phản hồi nhị phân có thể rất lớn; xem [API heapdump 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/heapdump.html).

Từ đặc điểm đó, cần đánh giá hai hậu quả:

1. **Dữ liệu:** chuỗi mật khẩu, token, nội dung yêu cầu, dữ liệu người dùng hoặc đối tượng đã giải mã có thể còn trong bộ nhớ. Không bảo đảm mọi bí mật đều xuất hiện, nhưng không được xem tệp này như bản thống kê vô hại.
2. **Tài nguyên:** việc thu thập, tạo tệp và truyền dữ liệu tiêu tốn tài nguyên; tác động cụ thể phụ thuộc kích thước heap, JVM và tải ứng dụng. Không dùng endpoint này làm phép thử sức khỏe định kỳ.

Quyền tải heapdump nên là quyền riêng, chỉ cấp khi có nhu cầu điều tra được xác định. Một tài khoản đọc log thường ngày không mặc nhiên cần quyền này.

Che giá trị ở `/env` không làm sạch nội dung heapdump. Nếu bí mật thực sự tồn tại trong tiến trình, việc giá trị bị che ở một phản hồi JSON không loại nó khỏi bộ nhớ.

### 2.2. Logfile: quyền đọc lịch sử ứng dụng

`GET /actuator/logfile` trả nội dung log file; với Spring MVC có thể dùng header `Range` để đọc một phần. Logfile chỉ có khi ứng dụng có nguồn tệp log phù hợp, chẳng hạn `logging.file.name` hoặc cấu hình tệp ngoài tương ứng. Xem [API logfile 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/logfile.html) và [danh mục endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Nếu ứng dụng chỉ ghi ra stdout, thêm tên `logfile` vào exposure không tự biến toàn bộ log của nền tảng/container thành một tệp có thể tải.

Log có thể chứa định danh người dùng, đường dẫn, tham số, stack trace, câu SQL hoặc dữ liệu do chương trình ghi ra. Biện pháp bảo vệ cần đi cùng kỷ luật ghi log: tránh ghi Authorization, cookie, mật khẩu, access token hoặc toàn bộ nội dung yêu cầu chứa dữ liệu riêng tư.

`Range: bytes=0-1023` chỉ thay đổi phần dữ liệu được tải, không giảm yêu cầu phân quyền. Người không được đọc toàn bộ log cũng không được đọc từng đoạn rồi ghép lại.

### 2.3. Env: che giá trị không đồng nghĩa giấu cấu trúc hệ thống

`GET /actuator/env` trả thông tin Environment; `/actuator/env/{property.name}` truy vấn một thuộc tính. Thông tin có thể gồm nguồn cấu hình, profile và nguồn gốc thuộc tính. Xem [API env 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/env.html).

Ngay khi các giá trị bị che, tên thuộc tính, profile, tên nguồn cấu hình hoặc đường dẫn nguồn vẫn có thể tiết lộ cách triển khai. Vì vậy, có thể cần hạn chế toàn bộ endpoint, không chỉ ẩn những khóa mang tên password.

Trong Spring Boot 3.3, `management.endpoint.env.show-values` điều khiển việc hiện giá trị:

| Giá trị | Ý nghĩa |
| --- | --- |
| `never` | Che giá trị |
| `when-authorized` | Chỉ hiện theo điều kiện được phép của endpoint |
| `always` | Cho phép hiện giá trị, trừ trường hợp có hàm làm sạch tùy chỉnh tiếp tục che |

Nếu dùng `when-authorized`, cần cấu hình vai trò của endpoint cẩn thận; mặc định người đã xác thực có thể được coi là được phép xem giá trị. **Điều kiện hiện giá trị và quyền truy cập URL là hai việc khác nhau.** Đặt `show-values: never` không ngăn truy cập URL; đặt `roles` cho endpoint cũng không thay thế quy tắc HTTP của Spring Security.

Không đặt `always` chỉ để hỗ trợ chẩn đoán nhanh. Bài thực hành giữ `never` kể cả với người có quyền đọc env. Cơ chế này được mô tả trong [phần làm sạch giá trị nhạy cảm](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.sanitization).

### 2.4. Nhóm endpoint thay đổi trạng thái

| Thao tác | Ảnh hưởng cần cân nhắc |
| --- | --- |
| `POST /actuator/loggers/{name}` | Đổi mức log; có thể tăng tải, dung lượng và lượng dữ liệu nhạy cảm bị ghi |
| `DELETE /actuator/caches/{name}` | Làm rỗng cache; có thể tăng tải lên nguồn dữ liệu hoặc làm thay đổi hành vi tạm thời |
| `POST /actuator/shutdown` | Dừng ứng dụng nếu endpoint được bật và khả dụng |
| Xóa phiên qua endpoint `sessions` khi có Spring Session | Có thể buộc người dùng mất phiên |

[API loggers](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html) mô tả POST với `configuredLevel`; [API shutdown](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/shutdown.html) mô tả thao tác dừng. Không xem quyền đọc cấu hình logger là quyền thay đổi nó.

Trong Spring Boot Actuator 3.3 thuần, `env` là endpoint đọc. Không suy luận có `POST /actuator/env` để cập nhật cấu hình từ những ví dụ thuộc Spring Cloud hoặc endpoint tùy chỉnh của hệ thống khác. Phải kiểm kê chính dependency và operation của ứng dụng đang bảo vệ.

## 3. Bốn lớp bảo vệ bổ sung cho nhau

| Lớp | Quyết định |
| --- | --- |
| Khả năng tồn tại | Endpoint nào được bật và đáp ứng điều kiện tạo bean? |
| Công bố qua giao thức | Endpoint nào xuất hiện qua HTTP hoặc JMX? |
| Quyền cho yêu cầu | Danh tính nào được dùng phương thức nào trên endpoint nào? |
| Vận hành và dữ liệu | Ai thu thập, lưu, xem, chuyển tiếp và xóa kết quả chẩn đoán? |

`enabled` và exposure không đồng nghĩa. Không đưa endpoint vào HTTP exposure không bảo đảm nó cũng bị tắt ở kênh khác. Ngược lại, `permitAll()` không làm một endpoint đã tắt trở nên có handler.

Với cấu hình exposure, danh sách loại trừ có ưu tiên hơn danh sách công bố. Nếu cấu hình nền đã loại `heapdump`, chỉ thêm nó vào `include` ở profile khác chưa chắc mở được. Phải kiểm tra cấu hình hiệu lực, không chỉ một tệp YAML.

Việc vô hiệu hóa discovery page hoặc đổi `/actuator` thành tên khác chỉ giảm khả năng tình cờ tìm thấy đường dẫn. Nó không xác thực hay phân quyền yêu cầu đã biết URL.

Cách tiếp cận tốt là công bố ít endpoint cần thiết, quy định quyền rõ ràng và mặc định từ chối những trường hợp chưa được xét.

## 4. Cấu hình nền: chỉ công bố health

Dưới đây là `src/main/resources/application.yml` của một dự án thử:

~~~yaml
spring:
  application:
    name: sensitive-actuator-lab
  jmx:
    enabled: false

management:
  endpoints:
    web:
      exposure:
        include: health
    jmx:
      exposure:
        exclude: "*"
  endpoint:
    health:
      show-details: never
    heapdump:
      enabled: false
    logfile:
      enabled: false
    env:
      enabled: false
    loggers:
      enabled: false
    caches:
      enabled: false
    shutdown:
      enabled: false
~~~

Ví dụ thể hiện chủ ý không dùng các khả năng nhạy cảm trong chế độ nền. Nó không chỉ giấu các liên kết trên giao diện.

JMX là kênh riêng: cấu hình HTTP và `SecurityFilterChain` Servlet không kiểm soát việc gọi MBean. `spring.jmx.enabled` tác động tới cơ chế do Spring quản lý, không nhất thiết tắt mọi MBean hay kênh quản trị do thư viện/JVM tự cung cấp; xem [quản trị qua JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

Không dựa duy nhất vào việc nhận 404 để chứng minh endpoint đã tắt. Một bộ lọc bảo mật có thể trả 401/403 trước khi MVC xác định không có handler. Cần đối chiếu cấu hình hiệu lực, mapping/bean thích hợp và hành vi truy cập.

## 5. Thực hành phân quyền trên profile cục bộ

Phần này tạo hai tài khoản:

- `analyst`: đọc env đã che giá trị và đọc logfile.
- `operator`: đọc/đổi mức log và đọc/xóa dữ liệu cache.

**Không tạo tài khoản có quyền heapdump mặc định.** Quy tắc cho heapdump vẫn được khai báo để yêu cầu một authority riêng khi hệ thống thực sự cấp quyền điều tra có kiểm soát.

Không dùng một vai trò ADMIN chung cho mọi hoạt động. Những tên authority sau là thiết kế của ví dụ, không phải tên quyền Spring Boot tự tạo.

### 5.1. Dependency và ứng dụng

Dự án cần Java 21, plugin Spring Boot 3.3.x, dependency management và Gradle Wrapper. Các khai báo cần có trong `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Các tệp Java bên dưới nằm trong `src/main/java/com/example/actuatorguard/`. Chúng là mã Spring trong dự án có dependency, không phải chương trình một tệp chạy bằng javac.

`GuardApplication.java`:

~~~java
package com.example.actuatorguard;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;

@SpringBootApplication
public class GuardApplication {
    public static void main(String[] args) {
        SpringApplication.run(GuardApplication.class, args);
    }

    @Bean
    @Profile("actuator-lab")
    CacheManager labCacheManager() {
        return new ConcurrentMapCacheManager("books");
    }
}
~~~

CacheManager giúp kiểm tra tác động xóa phần tử cache mà không cần kết nối cơ sở dữ liệu.

### 5.2. Chỉ mở khả năng chẩn đoán trong profile thử

Tạo `src/main/resources/application-actuator-lab.yml`:

~~~yaml
server:
  address: 127.0.0.1

management:
  endpoints:
    web:
      exposure:
        include: health,env,logfile,heapdump,loggers,caches
  endpoint:
    env:
      enabled: true
      show-values: never
    logfile:
      enabled: true
    heapdump:
      enabled: true
    loggers:
      enabled: true
    caches:
      enabled: true
    shutdown:
      enabled: false

logging:
  file:
    name: .actuator-lab/log/application.log
  level:
    com.example.actuatorguard.probe: INFO

lab:
  reader-password: ${LAB_READER_PASSWORD}
  operator-password: ${LAB_OPERATOR_PASSWORD}
  marker: safe-marker-not-a-secret
~~~

Profile ghi đè các cờ `enabled` cần dùng. Exposure không dùng `*`. Cấu hình JMX và việc tắt shutdown vẫn kế thừa từ tệp nền.

Heapdump được đưa vào profile để thử nhánh bị từ chối; **không chạy lệnh tải heapdump** trong bài. Một JVM không hỗ trợ heapdump hoặc môi trường thiếu điều kiện có thể không tạo được operation tương ứng.

Profile là công cụ chọn cấu hình, không phải ranh giới xác thực. Đừng kích hoạt profile thử ở môi trường thật rồi xem nó như chính sách vận hành hoàn chỉnh.

### 5.3. Tài khoản chỉ dành cho thí nghiệm

`LabAccounts.java`:

~~~java
package com.example.actuatorguard;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration(proxyBeanMethods = false)
@Profile("actuator-lab")
public class LabAccounts {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService labUsers(
            PasswordEncoder encoder,
            @Value("${lab.reader-password}") String readerPassword,
            @Value("${lab.operator-password}") String operatorPassword) {
        return new InMemoryUserDetailsManager(
            User.withUsername("analyst")
                .password(encoder.encode(readerPassword))
                .authorities("ACTUATOR_ENV_READ", "ACTUATOR_LOG_READ")
                .build(),
            User.withUsername("operator")
                .password(encoder.encode(operatorPassword))
                .authorities(
                    "ACTUATOR_LOGGERS_READ",
                    "ACTUATOR_LOGGERS_WRITE",
                    "ACTUATOR_CACHES_READ",
                    "ACTUATOR_CACHES_CLEAR")
                .build()
        );
    }
}
~~~

Hai mật khẩu lấy từ môi trường. Không dùng tài khoản này làm mẫu quản trị danh tính cho sản phẩm thật. Với hệ thống vận hành, ánh xạ các quyền qua nguồn danh tính được quản lý và cơ chế cấp/thu hồi phù hợp.

### 5.4. Phân quyền theo endpoint và HTTP method

`ActuatorSecurity.java`:

~~~java
package com.example.actuatorguard;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class ActuatorSecurity {
    private static RequestMatcher operation(String method, String... ids) {
        return new AndRequestMatcher(
            EndpointRequest.to(ids),
            request -> method.equals(request.getMethod())
        );
    }

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(operation("GET", "health")).permitAll()
                .requestMatchers(operation("GET", "heapdump"))
                    .hasAuthority("ACTUATOR_HEAPDUMP_READ")
                .requestMatchers(operation("GET", "logfile"))
                    .hasAuthority("ACTUATOR_LOG_READ")
                .requestMatchers(operation("GET", "env"))
                    .hasAuthority("ACTUATOR_ENV_READ")
                .requestMatchers(operation("GET", "loggers"))
                    .hasAuthority("ACTUATOR_LOGGERS_READ")
                .requestMatchers(operation("POST", "loggers"))
                    .hasAuthority("ACTUATOR_LOGGERS_WRITE")
                .requestMatchers(operation("GET", "caches"))
                    .hasAuthority("ACTUATOR_CACHES_READ")
                .requestMatchers(operation("DELETE", "caches"))
                    .hasAuthority("ACTUATOR_CACHES_CLEAR")
                .anyRequest().denyAll()
            )
            .httpBasic(withDefaults())
            .csrf(withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth.anyRequest().denyAll())
            .httpBasic(withDefaults())
            .csrf(withDefaults());
        return http.build();
    }
}
~~~

Các điểm cần đọc từ mã:

- `securityMatcher` chọn chuỗi áp dụng; các matcher bên trong chọn quyền của yêu cầu thuộc chuỗi đó.
- Helper kết hợp endpoint với method. GET loggers không tự cấp POST; GET caches không tự cấp DELETE.
- Matcher endpoint bao phủ các đường dẫn con như `/env/lab.marker` và `/caches/books`. Đây là lý do không chỉ kiểm tra một URL gốc.
- Header Range không đổi quyền: vẫn là GET tới logfile.
- `anyRequest().denyAll()` chặn trường hợp chưa có quy tắc, gồm endpoint mới được công bố sau này.
- Chuỗi dự phòng bảo vệ URL ngoài Actuator. Ứng dụng thật cần thay nó bằng chính sách nghiệp vụ của mình.
- Chỉ chuỗi đầu tiên khớp yêu cầu được dùng; các chuỗi không cộng dồn.

Ví dụ chủ động chỉ cho GET đọc. HEAD không được cấp tự động; không dùng HEAD vào heapdump như một phép kiểm tra rẻ vì handler GET có thể vẫn được thực thi để xây dựng phản hồi.

`hasAuthority` dùng nguyên tên quyền. `hasRole` lại áp dụng quy ước tiền tố ROLE_; không đổi hai hàm cho nhau mà giữ nguyên tên quyền.

API matcher có thể đối chiếu trong [mã nguồn EndpointRequest 3.3](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.java). Cách chọn chuỗi và phân quyền yêu cầu được trình bày trong [cấu hình Java của Spring Security](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html) và [phân quyền HTTP](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).

### 5.5. Xác thực đúng vẫn có thể bị CSRF chặn

Cấu hình giữ CSRF. Operator gửi POST đúng mật khẩu nhưng thiếu token vẫn có thể nhận 403. Token CSRF hợp lệ không cấp thêm authority; analyst có token cũng không được đổi mức log.

Không tắt CSRF toàn ứng dụng để sửa một lệnh thử. Nếu chuyển tuyến máy sang chỉ nhận Bearer header, cần kiểm chứng không nhận danh tính tự gửi qua cookie/Basic rồi mới chọn ngoại lệ có phạm vi. Gắn nhãn stateless không đủ chứng minh điều đó. Cơ chế mặc định được mô tả trong [CSRF Servlet nhánh 6.3](https://raw.githubusercontent.com/spring-projects/spring-security/6.3.x/docs/modules/ROOT/pages/servlet/exploits/csrf.adoc).

Phần kiểm thử dưới đây dùng trợ giúp CSRF của MockMvc để tập trung chứng minh quyền và tác động. Một giao diện vận hành thật còn cần luồng lấy/gửi token phù hợp với phiên và frontend của nó.

## 6. Thử các quyền đọc mà không tải heapdump

Chạy dự án thử từ PowerShell:

~~~powershell
$env:LAB_READER_PASSWORD = 'local-reader-only'
$env:LAB_OPERATOR_PASSWORD = 'local-operator-only'
.\gradlew.bat bootRun --args="--spring.profiles.active=actuator-lab"
~~~

Dùng mật khẩu thử cục bộ, không dùng tài khoản thật. Mở terminal thứ hai:

~~~powershell
$base = 'http://127.0.0.1:8080'

function New-LabBasicHeader([string]$account, [string]$password) {
    $bytes = [Text.Encoding]::UTF8.GetBytes("${account}:$password")
    @{ Authorization = 'Basic ' + [Convert]::ToBase64String($bytes) }
}

$reader = New-LabBasicHeader 'analyst' 'local-reader-only'
$operator = New-LabBasicHeader 'operator' 'local-operator-only'

$envResult = Invoke-WebRequest -UseBasicParsing `
    -Uri "$base/actuator/env/lab.marker" -Headers $reader
$envResult.StatusCode
($envResult.Content | ConvertFrom-Json).property.value
~~~

Kỳ vọng:

~~~text
200
******
~~~

Dấu sao là kết quả che giá trị, dù marker chỉ là dữ liệu giả. Quyền đọc env không tự bật việc hiện giá trị thô.

Đổi sang operator để kiểm tra bị từ chối:

~~~powershell
try {
    Invoke-WebRequest -UseBasicParsing `
        -Uri "$base/actuator/env/lab.marker" -Headers $operator |
        Out-Null
} catch {
    [int]$_.Exception.Response.StatusCode
}
~~~

Kỳ vọng `403`: operator được cấp quyền điều khiển một số thao tác, không được cấp quyền đọc env.

Ma trận mong muốn của profile thử:

| Yêu cầu | Không đăng nhập | Analyst | Operator |
| --- | --- | --- | --- |
| GET health khi ứng dụng khỏe | 200 | 200 | 200 |
| GET env và env/property | 401 | 200, giá trị bị che | 403 |
| GET logfile, có hoặc không có Range hợp lệ | 401 | Được đọc | 403 |
| GET heapdump | 401 | 403 | 403 |
| POST loggers với CSRF hợp lệ, dữ liệu hợp lệ | 401 | 403 | 204 |
| DELETE cache books với CSRF hợp lệ | 401 | 403 | 204 |

Các hàng ghi/xóa giả định token hợp lệ để cô lập kiểm tra danh tính và quyền. Thiếu token có thể bị 403 trước kiểm tra xác thực. Đọc log toàn phần thường trả 200; Range thỏa mãn có thể trả 206. Tệp không có hoặc Range không hợp lệ làm kết quả khác.

Không tự động tải heapdump để “thử thành công”. Nhánh từ chối giúp kiểm tra quyền của hai tài khoản mà không tạo tệp bộ nhớ. Muốn kiểm chứng nhánh được phép, cần một thử nghiệm riêng có dữ liệu giả và ngân sách tài nguyên được xác định.

## 7. Kiểm thử hồi quy cho ranh giới quyền

Tạo `src/test/java/com/example/actuatorguard/ActuatorGuardTest.java`:

~~~java
package com.example.actuatorguard;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.logging.LogLevel;
import org.springframework.boot.logging.LoggingSystem;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ActiveProfiles("actuator-lab")
@SpringBootTest(properties = {
    "lab.reader-password=reader-test-only",
    "lab.operator-password=operator-test-only",
    "logging.file.name=${java.io.tmpdir}/actuator-guard-test.log"
})
@AutoConfigureMockMvc
class ActuatorGuardTest {
    private static final String PROBE = "com.example.actuatorguard.probe";
    private static final String LOGGER = "/actuator/loggers/" + PROBE;
    private static final String BODY = "{\"configuredLevel\":\"DEBUG\"}";

    @Autowired MockMvc mvc;
    @Autowired CacheManager cacheManager;
    @Autowired LoggingSystem loggingSystem;

    private Cache books;

    @BeforeEach
    void prepareState() {
        books = cacheManager.getCache("books");
        assertNotNull(books);
        books.put("isbn", "draft");
        loggingSystem.setLogLevel(PROBE, LogLevel.INFO);
    }

    @Test
    void anonymousCannotReadEnvironment() throws Exception {
        mvc.perform(get("/actuator/env/lab.marker"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void analystReadsMaskedEnvironment() throws Exception {
        mvc.perform(get("/actuator/env/lab.marker")
                .with(httpBasic("analyst", "reader-test-only")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.property.value").value("******"));
    }

    @Test
    void operatorCannotReadEnvironmentSubpath() throws Exception {
        mvc.perform(get("/actuator/env/lab.marker")
                .with(httpBasic("operator", "operator-test-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void analystCanReadLogFile() throws Exception {
        mvc.perform(get("/actuator/logfile")
                .with(httpBasic("analyst", "reader-test-only")))
            .andExpect(status().isOk());
    }

    @Test
    void rangeDoesNotBypassLogPermission() throws Exception {
        mvc.perform(get("/actuator/logfile")
                .header("Range", "bytes=0-15")
                .with(httpBasic("operator", "operator-test-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void analystCannotDownloadHeap() throws Exception {
        mvc.perform(get("/actuator/heapdump")
                .with(httpBasic("analyst", "reader-test-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void analystCannotWriteLoggerEvenWithCsrf() throws Exception {
        mvc.perform(post(LOGGER)
                .with(httpBasic("analyst", "reader-test-only"))
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON).content(BODY))
            .andExpect(status().isForbidden());
        assertEquals(LogLevel.INFO,
            loggingSystem.getLoggerConfiguration(PROBE).getConfiguredLevel());
    }

    @Test
    void operatorNeedsCsrfForLoggerWrite() throws Exception {
        mvc.perform(post(LOGGER)
                .with(httpBasic("operator", "operator-test-only"))
                .contentType(MediaType.APPLICATION_JSON).content(BODY))
            .andExpect(status().isForbidden());
        assertEquals(LogLevel.INFO,
            loggingSystem.getLoggerConfiguration(PROBE).getConfiguredLevel());
    }

    @Test
    void operatorCanChangeLoggerWithCsrf() throws Exception {
        mvc.perform(post(LOGGER)
                .with(httpBasic("operator", "operator-test-only"))
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON).content(BODY))
            .andExpect(status().isNoContent());
        assertEquals(LogLevel.DEBUG,
            loggingSystem.getLoggerConfiguration(PROBE).getConfiguredLevel());
    }

    @Test
    void rejectedDeleteKeepsCacheData() throws Exception {
        mvc.perform(delete("/actuator/caches/books")
                .with(httpBasic("operator", "operator-test-only")))
            .andExpect(status().isForbidden());
        assertNotNull(books.get("isbn"));
    }

    @Test
    void authorizedDeleteClearsCacheData() throws Exception {
        mvc.perform(delete("/actuator/caches/books")
                .with(httpBasic("operator", "operator-test-only"))
                .with(csrf().asHeader()))
            .andExpect(status().isNoContent());
        assertNull(books.get("isbn"));
    }

    @Test
    void unlistedActuatorUrlIsDenied() throws Exception {
        mvc.perform(get("/actuator/beans")
                .with(httpBasic("operator", "operator-test-only")))
            .andExpect(status().isForbidden());
    }
}
~~~

Chạy:

~~~powershell
.\gradlew.bat test --tests com.example.actuatorguard.ActuatorGuardTest
~~~

Kỳ vọng 12 kiểm thử đạt khi dùng đúng cấu hình và môi trường mô tả. Bài thử chỉ dùng dữ liệu giả; không gọi nhánh tạo heapdump hoặc dừng JVM.

Các kiểm thử không chỉ nhìn trạng thái HTTP: chúng xác nhận logger không đổi khi bị từ chối và dữ liệu cache chỉ bị xóa khi đủ điều kiện.

Giới hạn cần hiểu:

- MockMvc dùng cùng context Servlet của ứng dụng thử, không chứng minh firewall/proxy ở môi trường triển khai.
- `csrf()` tạo yêu cầu phù hợp cho kiểm thử, không kiểm tra luồng lấy token của một trình duyệt thật.
- Bị chặn ở URL heapdump không chứng minh JVM có hỗ trợ việc tạo dump; cần kiểm kê mapping riêng nếu cần kiểm tra khả năng đó.
- 403 ở `/actuator/beans` chứng minh chính sách không cho yêu cầu đi tiếp, không chứng minh endpoint đã được tạo.
- Kiểm thử logfile cần quyền ghi tệp ở thư mục tạm; không phụ thuộc vào log vận hành thật.

## 8. Tách đường quản trị khỏi đường công khai

Khi đưa chính sách vào triển khai, cần kiểm tra cả đường đi mạng. Ví dụ cấu hình một cổng quản trị riêng:

~~~yaml
management:
  server:
    port: 9091
    address: 127.0.0.1
~~~

Đây là ví dụ triển khai riêng, không thêm vào cấu hình chung cổng của bài thử mà giữ nguyên kỳ vọng MockMvc. `management.server.address` chỉ có thể khác địa chỉ máy chủ chính khi cổng quản trị khác cổng chính.

`127.0.0.1` được hiểu theo môi trường mạng của tiến trình. Trong container, loopback thuộc container đó; không có nghĩa mọi thành phần trên máy chủ đều gọi được. Một proxy, tunnel hoặc cấu hình publish port sai vẫn có thể tạo đường truy cập ngoài ý muốn.

Cổng riêng không tự cung cấp TLS, mật khẩu hay phân quyền. Nếu truyền thông tin xác thực qua mạng, bảo vệ kênh truyền; kiểm tra cấu hình TLS của đường quản trị riêng thay vì suy ra từ cổng ứng dụng. Các thuộc tính liên quan có trong [quản trị HTTP 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

Cần thử từ ít nhất hai vị trí:

1. Nguồn vận hành được phép: kết nối tới đúng dịch vụ và nhận chính sách quyền mong muốn.
2. Nguồn không được phép: không thể vượt qua lớp mạng hoặc xác thực bằng đường khác, kể cả tên miền/IP/cổng trực tiếp.

Nếu dùng proxy danh tính, không để người gọi trực tiếp tự đặt header nhận dạng mà backend tin tưởng. Phải bảo vệ kết nối proxy–backend và loại bỏ header không đáng tin ở ranh giới phù hợp.

Đổi base path hoặc ẩn liên kết không thay thế các lớp này. Không đưa endpoint quản trị vào CDN/public cache; không để dump và log tải xuống trở thành static asset có URL công khai.

## 9. Quản lý kết quả chẩn đoán sau khi lấy

Phân quyền HTTP kết thúc ở lúc chuyển dữ liệu cho người được phép. Tệp đã tải còn cần vòng đời riêng:

- Xác định người điều tra, mục đích và phạm vi dữ liệu thật sự cần.
- Chỉ cấp quyền đặc biệt trong khoảng thời gian cần thiết; thu hồi sau khi kết thúc.
- Với heapdump, đánh giá dung lượng, dung lượng đĩa, tải và tác động JVM trước khi thu thập.
- Lưu tệp ở nơi có kiểm soát truy cập và cơ chế bảo vệ dữ liệu phù hợp; không đính kèm dump nguyên bản vào issue công khai.
- Giới hạn người xem, thời gian lưu và việc chuyển cho bên thứ ba.
- Ghi nhận ai truy cập, endpoint, thời điểm và kết quả; không ghi lại mật khẩu/token hay nội dung nhạy cảm chỉ để làm audit.
- Sau điều tra, đóng exposure/quyền tạm và xử lý bản sao theo chính sách lưu giữ.

Ví dụ: mở env đã che để tìm nguồn ghi đè cấu hình có thể đủ cho một sự cố. Điều đó không tự tạo lý do tải toàn bộ heap. Quyền được chọn theo câu hỏi cần giải quyết, thay vì luôn cấp toàn bộ khả năng chẩn đoán.

Nếu nghi ngờ đã lộ dump hoặc log chứa thông tin xác thực, chỉ đóng URL không vô hiệu hóa những bản sao đã lấy. Cần đánh giá dữ liệu liên quan và thay thế/thu hồi thông tin xác thực có thể bị lộ.

## 10. Những lỗi thiết kế thường gặp

| Cách làm | Vì sao không đủ |
| --- | --- |
| `include: "*"` rồi cho mọi người đã đăng nhập truy cập | Tài khoản thông thường có thể nhận quyền chẩn đoán hoặc điều khiển quá rộng |
| Chỉ chặn POST/DELETE | Bỏ sót rủi ro lộ dữ liệu qua GET heapdump/logfile/env |
| Chỉ đặt env `show-values: never` | Không chặn truy cập metadata và không làm sạch log/heapdump |
| Dùng `when-authorized` mà không xét điều kiện vai trò | Có thể mở giá trị thô cho nhóm người rộng hơn dự định |
| Cấp cùng một quyền đọc log và tải heap | Không thể giới hạn quyền điều tra bộ nhớ riêng |
| Kiểm tra quyền URL gốc nhưng bỏ sót đường con | Có thể không bảo vệ env/property hoặc thao tác cache cụ thể |
| Mở đọc từng đoạn logfile cho mọi người | Các đoạn vẫn có thể chứa thông tin nhạy cảm hoặc được ghép lại |
| Tắt CSRF chỉ để POST trả thành công | Bỏ qua nguyên nhân và điều kiện xác thực của luồng trình duyệt |
| Chỉ bảo vệ ở proxy, backend vẫn truy cập trực tiếp | Có thể đi vòng chính sách ở đường kết nối khác |
| Tắt HTTP nhưng quên kênh JMX được bật riêng | Khả năng quản trị có thể còn qua giao thức khác |
| Kiểm thử bằng tải dump hoặc shutdown trên ứng dụng thật | Bản thân phép thử có thể làm lộ dữ liệu hoặc gián đoạn |

Không phải endpoint tùy chỉnh nào cũng thể hiện tác động đúng trong tên. Cần rà soát operation, phương thức HTTP và mã thực thi của những endpoint do ứng dụng hoặc thư viện bổ sung, rồi đưa vào chính sách mặc định từ chối trước khi cấp quyền có chủ đích.

## 11. Tự kiểm tra mức hiểu

1. Vì sao một hệ thống chỉ cho phép GET vẫn có thể lộ dữ liệu nghiêm trọng qua Actuator?
2. Analyst có thể đọc env đã che nhưng không đọc heapdump: ranh giới quyền này bảo vệ điều gì?
3. Vì sao đổi `show-values` không làm token từng ghi vào logfile biến mất?
4. Operator bị 403 khi POST logger. Làm sao phân biệt thiếu quyền với thiếu token CSRF mà không tắt kiểm tra?
5. Tại sao kiểm thử Range và đường dẫn con có giá trị hơn chỉ thử `/actuator`?
6. Khi chuyển từ cùng cổng sang cổng quản trị riêng, những giả định nào về context, mạng và TLS cần được kiểm chứng lại?
7. Sau khi đóng endpoint heapdump, những rủi ro nào của tệp đã tải vẫn tồn tại?

Một chính sách tốt phải trả lời được: **endpoint nào thực sự cần tồn tại, xuất hiện ở kênh nào, ai được làm thao tác gì và dữ liệu chẩn đoán được quản lý ra sao sau khi lấy**.

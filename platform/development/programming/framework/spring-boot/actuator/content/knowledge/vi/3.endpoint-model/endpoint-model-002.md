# Phân biệt endpoint được bật, được công bố và được phép truy cập

## 1. Một endpoint có thể “có” theo nhiều nghĩa

Bạn thêm Actuator, thấy cấu hình `info.enabled=true` nhưng gọi `/actuator/info` không lấy được dữ liệu. Sau đó thêm tên `info` vào danh sách công bố, yêu cầu lại trả `401`. Khi đăng nhập bằng một tài khoản khác, nó trả `403`.

Ba kết quả này không nhất thiết mâu thuẫn. Bạn đang gặp những lớp quyết định khác nhau:

| Câu hỏi | Khái niệm tương ứng |
| --- | --- |
| Khả năng endpoint có được bật theo cấu hình không? | Được bật — enabled |
| Endpoint có được công bố qua HTTP hoặc JMX không? | Được công bố — exposed |
| Yêu cầu từ danh tính này có đáp ứng chính sách truy cập không? | Được phép truy cập — authorized |

**Bật không đồng nghĩa công bố; công bố không đồng nghĩa cấp quyền cho mọi người.**

Bài dùng Spring Boot **3.3.13**, Java **21** và ứng dụng Servlet. Ví dụ kiểm chứng ba lớp bằng endpoint chuẩn `info`. Không cần tạo API nghiệp vụ giả để có dữ liệu quan sát.

Các thuộc tính `enabled` trong bài thuộc hợp đồng của dòng Boot 3.3. Khi chuyển phiên bản lớn hoặc nhỏ khác, hãy đối chiếu tài liệu phiên bản đó thay vì trộn các mô hình cấu hình.

## 2. Được bật: quyết định về khả năng endpoint

### 2.1. Thuộc tính riêng của một endpoint

Trong Boot 3.3:

~~~yaml
management:
  endpoint:
    info:
      enabled: true
~~~

Đoạn này nói rằng endpoint `info` được bật theo cấu hình. Đặt `false` sẽ vô hiệu hóa endpoint tương ứng trong cơ chế tự cấu hình đang xét.

Nếu muốn mặc định không bật các endpoint rồi chọn từng cái:

~~~yaml
management:
  endpoints:
    enabled-by-default: false
  endpoint:
    health:
      enabled: true
~~~

Đây là một cấu hình minh họa riêng cho cơ chế bật/tắt, không phải tệp cấu hình của bài thực hành bên dưới. [Spring Boot 3.3: bật endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.enabling).

Chú ý hai tên:

- `management.endpoint.info.enabled` dùng `endpoint` số ít cho endpoint cụ thể.
- `management.endpoints.enabled-by-default` dùng `endpoints` cho chính sách chung.

Ghi sai tên thuộc tính có thể khiến bạn đang suy luận dựa trên một giá trị chưa từng được áp dụng.

### 2.2. enabled=true chưa đảm bảo luôn có bean

Đối với endpoint tích hợp sẵn như `info`, còn có điều kiện tự cấu hình. Boot xét khả năng sẵn có của endpoint, gồm trạng thái bật và công nghệ công bố phù hợp.

Vì vậy, không nên dùng lập luận:

~~~text
Đã ghi enabled=true
    -> chắc chắn có một InfoEndpoint bean
    -> chắc chắn có URL HTTP
~~~

`InfoEndpointAutoConfiguration` dùng điều kiện `@ConditionalOnAvailableEndpoint`; việc tạo thành phần còn phụ thuộc điều kiện đó. [API tự cấu hình InfoEndpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/info/InfoEndpointAutoConfiguration.html), [ConditionalOnAvailableEndpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/endpoint/condition/ConditionalOnAvailableEndpoint.html).

Ví dụ của bài cố ý giữ `info` được công bố qua JMX ở một lượt chạy. Nhờ đó có thể chứng minh rõ trường hợp **bean tồn tại nhưng HTTP không được công bố**.

## 3. Được công bố: luôn phải hỏi “qua cơ chế nào?”

### 3.1. Công bố qua HTTP

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Đây là lựa chọn các định danh endpoint được công bố qua web. Với đường dẫn mặc định trong ứng dụng mẫu, `info` có thể được ánh xạ tới `/actuator/info`.

Nếu có cả include và exclude:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
        exclude: info
~~~

Thì `info` vẫn bị loại khỏi công bố HTTP, vì exclude có ưu tiên trong quyết định này. [Cấu hình exposure](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

Việc thêm `info` vào include không tự bật lại endpoint đã bị tắt. Nó cũng không tự tạo các phụ thuộc hoặc bean mà endpoint cần.

### 3.2. Công bố qua JMX là quyết định riêng

~~~yaml
spring:
  jmx:
    enabled: true

management:
  endpoints:
    jmx:
      exposure:
        include: info
~~~

Cấu hình này chọn công bố `info` qua JMX. Nó không tự thêm `info` vào danh sách HTTP.

Trong cấu hình tên/domain mặc định của bài, ObjectName của MBean info là:

~~~text
org.springframework.boot:type=Endpoint,name=Info
~~~

Bật hỗ trợ JMX, đăng ký MBean và cấu hình một kết nối JMX từ xa là các vấn đề riêng. Bài chỉ kiểm chứng qua `MBeanServer` ngay trong tiến trình, không mở connector JMX từ xa. [Actuator qua JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

### 3.3. Một bảng có đủ tên công nghệ sẽ rõ hơn một từ “exposed”

Thay vì ghi:

~~~text
info: exposed
~~~

Hãy mô tả cụ thể:

~~~text
info: bật
HTTP: không công bố
JMX: công bố
~~~

Cách ghi này giúp tránh kết luận “không gọi được URL nên endpoint đã bị tắt”.

## 4. Được phép truy cập: thuộc về yêu cầu và danh tính

Một endpoint đã được công bố qua HTTP vẫn có thể yêu cầu:

- Chứng minh danh tính — xác thực (authentication).
- Có quyền hoặc vai trò phù hợp — phân quyền (authorization).
- Đi qua đúng đường mạng và cơ chế quản trị được thiết kế.

Trong ví dụ:

| Danh tính | Trạng thái | Quyền đối với info được công bố |
| --- | --- | --- |
| Không gửi tài khoản | Chưa xác thực | Không được đọc |
| `reader` | Có vai trò `READER` | Không đủ quyền đọc |
| `operator` | Có vai trò `OPS` | Được đọc |

Đăng nhập thành công không đồng nghĩa có mọi quyền. Ngược lại, một endpoint công khai có thể không yêu cầu đăng nhập.

Spring Security cho phép đặt quy tắc theo yêu cầu. Khi tự cấu hình `SecurityFilterChain`, người viết phải xác định đầy đủ chính sách cho phạm vi ứng dụng của mình. [Phân quyền yêu cầu HTTP](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).

Bài dùng HTTP Basic để nhìn rõ các trạng thái. Đây là mô hình tài khoản trong bộ nhớ phục vụ thực hành trên loopback; khi dùng qua mạng trong môi trường triển khai, thông tin đăng nhập cần đi trên đường truyền được bảo vệ phù hợp.

## 5. Ba lớp là mô hình suy luận, không phải thứ tự xử lý vật lý

Có thể dùng mô hình logic sau để phân tích một yêu cầu:

~~~text
Endpoint được bật?
    + có điều kiện tạo thành phần?
    + được công bố qua đúng công nghệ?
    + URL/cổng/phương thức phù hợp?
    + yêu cầu được phép?
    -> mới có thể thực hiện thao tác endpoint
~~~

Nhưng đừng biến nó thành khẳng định rằng server luôn kiểm tra theo đúng thứ tự từ trên xuống. Trong ứng dụng Servlet, các bộ lọc bảo mật có thể chạy trước khi Spring MVC tìm handler cuối cùng.

Hệ quả quan trọng:

> Một mã 401 không đủ để kết luận endpoint tồn tại.

Một đường dẫn không có handler vẫn có thể bị chính sách tổng quát yêu cầu xác thực chặn lại. Sau khi dùng tài khoản hợp lệ, bạn mới thấy `404`.

Tương tự, `404` một mình không cho biết endpoint bị tắt, không được công bố, sai cổng hay sai đường dẫn. Cần kết hợp cấu hình và bằng chứng khác.

Mô hình này cũng không đảm bảo “được phép” luôn trả `200`. Ví dụ, health có thể được gọi thành công nhưng báo tình trạng xấu bằng mã `503`. Quyền thực hiện và kết quả của thao tác là hai vấn đề khác nhau.

## 6. Dự án thực hành: quan sát info ở cả HTTP và JMX

### 6.1. Cấu trúc và mục tiêu

~~~text
endpoint-gates/
├── pom.xml
└── src/main/
    ├── java/example/endpointgates/
    │   ├── EndpointGatesApplication.java
    │   └── DemoSecurityConfiguration.java
    └── resources/application.yml
~~~

Cần JDK 21, Maven và khả năng tải thư viện lần đầu.

Ứng dụng sẽ:

1. Cung cấp một mẩu info cố định, không nhạy cảm.
2. In kết quả kiểm tra bean info và MBean JMX khi khởi động.
3. Cho health được đọc công khai.
4. Yêu cầu vai trò OPS cho những endpoint Actuator khác được công bố.
5. Dùng cùng JAR cho bốn lượt cấu hình.

### 6.2. pom.xml

~~~xml
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
    <artifactId>endpoint-gates</artifactId>
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
~~~

### 6.3. Lớp khởi động và phép kiểm tra trong tiến trình

Tệp `src/main/java/example/endpointgates/EndpointGatesApplication.java`:

~~~java
package example.endpointgates;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.boot.actuate.info.InfoEndpoint;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class EndpointGatesApplication {
    public static void main(String[] args) {
        SpringApplication.run(EndpointGatesApplication.class, args);
    }

    @Bean
    InfoContributor lessonInfo() {
        return builder -> builder.withDetail("lesson", "endpoint-gates");
    }

    @Bean
    ApplicationRunner inspectInfo(ApplicationContext context, MBeanServer mbeans) {
        return args -> {
            ObjectName name =
                new ObjectName("org.springframework.boot:type=Endpoint,name=Info");
            boolean registered = mbeans.isRegistered(name);
            boolean readable = registered
                && mbeans.invoke(name, "info", new Object[0], new String[0]) != null;

            System.out.println("info.bean=" +
                !context.getBeansOfType(InfoEndpoint.class).isEmpty());
            System.out.println("info.jmx.registered=" + registered);
            System.out.println("info.jmx.read=" + readable);
        };
    }
}
~~~

`InfoContributor` thêm dữ liệu `lesson` cho endpoint `info`. Nó không phải controller và không tự công bố một URL.

`InfoEndpoint` là endpoint chuẩn có thao tác đọc `info()`. [API InfoEndpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/info/InfoEndpoint.html).

Runner kiểm tra ba bằng chứng:

- `info.bean`: có bean `InfoEndpoint` trong context hay không.
- `info.jmx.registered`: MBean info đã được đăng ký hay chưa.
- `info.jmx.read`: lời gọi đọc trực tiếp qua MBeanServer có nhận kết quả hay không.

Đây là phép kiểm tra JMX từ mã đang chạy **trong cùng tiến trình**. Nó không dùng tài khoản HTTP và không chứng minh một người ở ngoài máy đã có quyền JMX từ xa.

### 6.4. Cấu hình hai tài khoản và quyền HTTP

Tệp `src/main/java/example/endpointgates/DemoSecurityConfiguration.java`:

~~~java
package example.endpointgates;

import jakarta.servlet.DispatcherType;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class DemoSecurityConfiguration {
    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${DEMO_READER_PASSWORD}") String readerPassword,
            @Value("${DEMO_OPERATOR_PASSWORD}") String operatorPassword) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode(readerPassword))
                .roles("READER")
                .build(),
            User.withUsername("operator")
                .password(encoder.encode(operatorPassword))
                .roles("OPS")
                .build()
        );
    }

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(requests -> requests
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(EndpointRequest.to(HealthEndpoint.class)).permitAll()
                .requestMatchers(EndpointRequest.toAnyEndpoint()).hasRole("OPS")
                .anyRequest().authenticated())
            .httpBasic(withDefaults());
        return http.build();
    }
}
~~~

Hai mật khẩu được lấy từ biến môi trường. Chương trình mã hóa chúng cho kho tài khoản trong bộ nhớ; YAML và mã nguồn không chứa mật khẩu thực hành.

Quy tắc có thứ tự:

1. Cho phép xử lý dispatch lỗi nội bộ.
2. Cho phép đọc health.
3. Với endpoint Actuator khác được matcher nhận diện, yêu cầu vai trò OPS.
4. Những yêu cầu còn lại phải được xác thực.

`EndpointRequest` nhận diện vị trí Actuator để không phải tự coi mọi đường dẫn trùng tiền tố là cùng một loại tài nguyên. [API EndpointRequest](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html).

`roles("OPS")` tạo quyền với tiền tố vai trò tương ứng; `hasRole("OPS")` kiểm tra vai trò đó. Chỉ có tên `operator` thôi chưa đủ: chính quyền được gán mới quyết định kết quả phân quyền.

Dòng `dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()` cho phép dispatch lỗi nội bộ giữ được cách báo lỗi. Nó không phải quy tắc công khai mọi yêu cầu ban đầu: yêu cầu ban đầu vẫn phải đi qua các quy tắc phía sau.

`anyRequest().authenticated()` là lý do một URL không tồn tại trong mẫu vẫn có thể trả `401` khi chưa gửi tài khoản. Sau khi xác thực hợp lệ, yêu cầu có thể đi tới định tuyến và nhận `404`.

Bài tự khai báo chuỗi bảo mật, nên không dựa vào việc Boot tiếp tục tự giữ toàn bộ quy tắc Actuator mặc định. HTTP Basic cũng được bật rõ bằng `httpBasic(withDefaults())`. [HTTP Basic trong Spring Security](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html).

### 6.5. Cấu hình ban đầu

Tệp `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: endpoint-gates
  jmx:
    enabled: true

server:
  address: 127.0.0.1
  port: 18090

management:
  endpoint:
    info:
      enabled: true
    health:
      show-details: never
  endpoints:
    web:
      exposure:
        include: health
    jmx:
      exposure:
        include: info
~~~

Ở cấu hình gốc:

- Info được bật.
- Web chỉ công bố health.
- JMX công bố info.
- HTTP chỉ lắng nghe trên `127.0.0.1:18090`.

Đây là nền để kiểm chứng rằng một endpoint có thể tồn tại và dùng qua JMX trong khi không có URL HTTP tương ứng.

Không tự thêm ký tự đại diện vào danh sách công bố để “sửa” mọi lỗi. Từng lượt bên dưới chỉ thay những thuộc tính cần thiết cho phép thử.

## 7. Build và chuẩn bị tài khoản thực hành

### 7.1. Tạo JAR

Tại thư mục chứa `pom.xml`:

~~~powershell
java -version
mvn -v
mvn clean package
~~~

Đảm bảo Maven sử dụng JDK 21. JAR dùng cho các lượt chạy là:

~~~text
target/endpoint-gates-1.0.0.jar
~~~

Maven biên dịch hai tệp Java và đóng gói các thư viện cần thiết. Không chạy riêng một tệp bằng `javac` mà thiếu classpath Spring Boot/Security.

### 7.2. Cấp mật khẩu ở Terminal A

Các lệnh sau dành cho PowerShell:

~~~powershell
$readerSecret = Read-Host "Mật khẩu thực hành của reader" -AsSecureString
$operatorSecret = Read-Host "Mật khẩu thực hành của operator" -AsSecureString

$env:DEMO_READER_PASSWORD = [System.Net.NetworkCredential]::new("", $readerSecret).Password
$env:DEMO_OPERATOR_PASSWORD = [System.Net.NetworkCredential]::new("", $operatorSecret).Password
~~~

Không in các biến ra để kiểm tra. Đây là bí mật của bài thực hành, không lấy mật khẩu tài khoản khác đang sử dụng.

Giá trị phải có trong terminal khởi chạy Java. Ở Terminal B, các lệnh `curl.exe --user reader` hoặc `--user operator` sẽ hỏi mật khẩu tương tác. Vì không ghi mật khẩu sau tên tài khoản trong lệnh, nó không bị đưa thẳng vào dòng lệnh đã lưu.

Trên Linux hoặc macOS có thể dùng `curl`; những lệnh nhập biến phía trên là cú pháp PowerShell.

## 8. Lượt A: bị tắt dù tên có trong danh sách công bố

Dùng Terminal A:

~~~powershell
java -jar target/endpoint-gates-1.0.0.jar --management.endpoint.info.enabled=false "--management.endpoints.web.exposure.include=health,info"
~~~

Tham số chạy ghi đè các giá trị tương ứng của YAML trong lượt này.

Sau khi khởi động, ba dòng do runner in là:

~~~text
info.bean=false
info.jmx.registered=false
info.jmx.read=false
~~~

Các dòng log khác của Boot vẫn có thể xuất hiện; ba dòng trên là phần kết quả cố định mà mã kiểm chứng của bài tạo.

Tại Terminal B, đọc info bằng tài khoản operator:

~~~powershell
curl.exe --silent --show-error --user operator --header "Accept: application/json" --output NUL --write-out "%{http_code}" http://127.0.0.1:18090/actuator/info
~~~

Nhập đúng mật khẩu operator. Mã HTTP là:

~~~text
404
~~~

Kết luận từ **cả cấu hình lẫn bằng chứng**: việc ghi `info` vào danh sách web và JMX không thắng được `enabled=false` trong endpoint tự cấu hình đang xét.

Không nên chỉ từ `404` rồi nói endpoint chắc chắn bị tắt. Lượt tiếp theo sẽ cho cùng mã HTTP nhưng trạng thái bean khác.

Dừng ứng dụng bằng `Ctrl+C` trước khi chuyển lượt.

## 9. Lượt B: bật và dùng được qua JMX, chưa công bố HTTP

Chạy đúng cấu hình gốc:

~~~powershell
java -jar target/endpoint-gates-1.0.0.jar
~~~

Ba dòng kết quả:

~~~text
info.bean=true
info.jmx.registered=true
info.jmx.read=true
~~~

Gọi lại info bằng operator:

~~~powershell
curl.exe --silent --show-error --user operator --header "Accept: application/json" --output NUL --write-out "%{http_code}" http://127.0.0.1:18090/actuator/info
~~~

Kết quả vẫn là:

~~~text
404
~~~

Nhưng lần này, info đã tồn tại và lời gọi JMX trong tiến trình đã đọc được kết quả. Điều chưa có là **công bố info qua HTTP**.

Cho dù operator có quyền OPS, quyền đó không tự tạo đường dẫn HTTP đang thiếu.

Trong cùng lượt này, thử một yêu cầu không có tài khoản:

~~~powershell
curl.exe --silent --show-error --header "Accept: application/json" --output NUL --write-out "%{http_code}" http://127.0.0.1:18090/actuator/info
~~~

Kết quả trong chính sách của mẫu:

~~~text
401
~~~

Đây là bằng chứng cụ thể rằng `401` có thể xuất hiện trước khi bên gọi nhìn thấy `404` của định tuyến. Nó không chứng minh info đã được công bố qua web.

`NUL` bỏ nội dung phản hồi trên Windows. Trên Linux/macOS, dùng `/dev/null` ở vị trí đó.

Dừng ứng dụng trước khi chuyển lượt.

## 10. Lượt C: công bố HTTP rồi phân biệt 401, 403 và 200

### 10.1. Công bố info qua web

Terminal A:

~~~powershell
java -jar target/endpoint-gates-1.0.0.jar "--management.endpoints.web.exposure.include=health,info"
~~~

Ba dòng kết quả vẫn là:

~~~text
info.bean=true
info.jmx.registered=true
info.jmx.read=true
~~~

Khác biệt với lượt B là lớp công bố HTTP đã có info.

### 10.2. Chưa gửi tài khoản

~~~powershell
curl.exe --silent --show-error --header "Accept: application/json" --output NUL --write-out "%{http_code}" http://127.0.0.1:18090/actuator/info
~~~

Kết quả:

~~~text
401
~~~

Trong cơ chế HTTP Basic của mẫu, yêu cầu này chưa có danh tính đã xác thực đáp ứng chính sách. Mật khẩu sai cũng là vấn đề xác thực, không phải cách chứng minh người đó có vai trò.

### 10.3. reader đã xác thực nhưng thiếu vai trò

~~~powershell
curl.exe --silent --show-error --user reader --header "Accept: application/json" --output NUL --write-out "%{http_code}" http://127.0.0.1:18090/actuator/info
~~~

Sau khi nhập đúng mật khẩu reader:

~~~text
403
~~~

Reader có tài khoản hợp lệ nhưng chỉ có vai trò READER. Quy tắc cho endpoint đang công bố yêu cầu OPS.

Đổi exposure không biến READER thành OPS. Đây là quyết định phân quyền, không phải bật/tắt endpoint.

### 10.4. operator có vai trò phù hợp

Đọc nội dung:

~~~powershell
curl.exe --silent --show-error --user operator --header "Accept: application/json" http://127.0.0.1:18090/actuator/info
~~~

Nội dung JSON:

~~~json
{"lesson":"endpoint-gates"}
~~~

Kiểm tra riêng mã HTTP bằng lệnh có `--output NUL --write-out` của các lượt trước, dùng operator; kết quả là `200`.

Ba danh tính đang gọi **cùng URL của cùng một tiến trình và cùng cấu hình công bố**. Khác biệt kết quả nằm ở yêu cầu và quyền.

### 10.5. Health được cho phép theo quy tắc riêng

~~~powershell
curl.exe --silent --show-error http://127.0.0.1:18090/actuator/health
~~~

Khi các phép kiểm tra mặc định đều đạt:

~~~json
{"status":"UP"}
~~~

Health công khai không làm info trở thành công khai. Quy tắc của một endpoint không phải quyền chung cho mọi endpoint khác.

Dừng ứng dụng trước khi chuyển lượt.

## 11. Lượt D: exclude loại info khỏi HTTP dù include có tên nó

Terminal A:

~~~powershell
java -jar target/endpoint-gates-1.0.0.jar "--management.endpoints.web.exposure.include=health,info" "--management.endpoints.web.exposure.exclude=info"
~~~

Ba dòng:

~~~text
info.bean=true
info.jmx.registered=true
info.jmx.read=true
~~~

Đọc info bằng operator qua HTTP trả `404`. JMX vẫn còn vì bạn chỉ loại info khỏi công bố **web**, không thay danh sách JMX của mẫu.

Bảng kết quả toàn bộ phép thử:

| Lượt | Bean info | Đọc JMX trong tiến trình | HTTP không tài khoản | HTTP reader hợp lệ | HTTP operator hợp lệ |
| --- | --- | --- | --- | --- | --- |
| A — enabled=false | Không | Không | 401 | 404 | 404 |
| B — chỉ JMX | Có | Có | 401 | 404 | 404 |
| C — có HTTP | Có | Có | 401 | 403 | 200 |
| D — web exclude info | Có | Có | 401 | 404 | 404 |

Các mã trong bảng thuộc **đúng quy tắc bảo mật và định tuyến của mẫu**. Không dùng chúng như quy tắc cứng cho mọi ứng dụng có proxy, gateway hoặc chính sách lỗi khác.

Điểm cần thấy là A và B có thể giống nhau về HTTP nhưng khác trạng thái endpoint; B và C có thể giống nhau về bean/JMX nhưng khác công bố HTTP; ở C, chính danh tính làm kết quả đổi.

## 12. Cách chẩn đoán đúng lớp

### Khi chưa kết nối được

Kiểm tra tiến trình, địa chỉ và cổng trước. Không có phản hồi HTTP thì chưa có cơ sở quy lỗi cho vai trò hoặc danh sách công bố.

Tách riêng lỗi kết nối khỏi một mã HTTP do ứng dụng trả. Cổng quản trị khác cổng ứng dụng cũng có thể khiến bạn đang gọi nhầm nơi.

### Khi có 404

Xác minh endpoint ID, tiền tố, cổng và công nghệ công bố. Sau đó xem enabled, include/exclude và điều kiện tự cấu hình.

Không sửa bảo mật theo kiểu `permitAll` chỉ để tìm một endpoint đang không được công bố. Cho phép một đường đi không tạo ra handler còn thiếu.

### Khi có 401

Kiểm tra cơ chế xác thực và thông tin gửi kèm. Nhưng vẫn giữ câu hỏi endpoint có thực sự được công bố hay không: quy tắc bảo mật dự phòng có thể chặn cả đường dẫn không tồn tại như lượt B.

### Khi có 403

Kiểm tra quyền của danh tính và điều kiện của yêu cầu. Ở lượt C của bài, nguyên nhân là thiếu vai trò OPS.

Trong tình huống khác, `403` còn có thể liên quan tới những bảo vệ khác. Chẳng hạn, yêu cầu POST có thể bị CSRF chặn. Bài chỉ dùng GET và không tắt CSRF để “sửa” mọi mã `403`. [Spring Security: CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).

### Khi truy cập được nhưng thiếu dữ liệu

Phân biệt quyền gọi endpoint với nội dung mà endpoint được cấu hình trả. Ví dụ, quyền gọi health không tự làm health hiển thị chi tiết; info cần nguồn đóng góp dữ liệu có ý nghĩa.

Giảm chi tiết phản hồi cũng không tương đương với tắt endpoint hoặc ngăn mọi người gọi nó.

## 13. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách suy luận chính xác hơn |
| --- | --- |
| `enabled=true` nghĩa là có URL | Cần xét điều kiện thành phần và công bố qua HTTP |
| Có trong include nghĩa là công khai | Còn quyết định xác thực và phân quyền |
| Tài khoản mạnh tự gọi được endpoint bị tắt | Quyền không tự tạo lại khả năng bị vô hiệu hóa |
| Xóa khỏi web exposure là tắt toàn bộ endpoint | Endpoint có thể còn được công bố qua JMX |
| `permitAll` sẽ khắc phục mọi 404 | Cấp quyền không tạo định tuyến hoặc bean đang thiếu |
| 401 chứng minh endpoint tồn tại | Chính sách chung có thể chặn trước bước tìm handler |
| 403 luôn nghĩa là sai mật khẩu | Cần phân biệt xác thực, quyền và những bảo vệ khác |
| Đọc được health là được đọc mọi Actuator | Mỗi nhóm yêu cầu có thể có quy tắc riêng |

Trong một hệ thống thật, hãy mô tả quyền theo **thao tác và danh tính**. Một endpoint quản trị có thao tác ghi không nên được coi giống một phép đọc chỉ vì chúng cùng thuộc Actuator.

## 14. Tự kiểm tra bằng các thay đổi nhỏ

**Bài 1 — Bỏ info khỏi JMX ở lượt B.**

Giữ web chỉ có health và bỏ công bố info qua JMX. Với endpoint tự cấu hình của Boot trong mẫu, hãy kiểm tra lại bean thay vì cố giữ giả định rằng enabled=true luôn tạo bean.

Mục tiêu là hiểu điều kiện “available”, không chỉ thuộc tên thuộc tính enabled.

**Bài 2 — Giữ nguyên cấu hình lượt C nhưng đổi vai trò reader.**

Nếu reader được gán OPS bằng mã cấu hình tài khoản rồi build lại, dự đoán kết quả HTTP của reader. Cần đổi quyền, không cần đổi exposure.

**Bài 3 — Dùng operator ở lượt A.**

Giải thích vì sao operator vẫn nhận 404 dù có vai trò cần cho info ở lượt C. Endpoint bị tắt và yêu cầu không đủ quyền là hai tình huống khác nhau.

**Bài 4 — Viết báo cáo lỗi có đủ ba lớp.**

Thay cho câu “Actuator không hoạt động”, hãy ghi endpoint nào, công nghệ nào, trạng thái enabled/exposure đã kiểm tra, danh tính dùng thử và phản hồi nhận được. Chỉ ghi phần dữ liệu cần thiết; không đưa mật khẩu vào báo cáo.

Sau khi dừng ứng dụng, có thể bỏ các biến mật khẩu của terminal thực hành:

~~~powershell
Remove-Item Env:DEMO_READER_PASSWORD, Env:DEMO_OPERATOR_PASSWORD -ErrorAction SilentlyContinue
Remove-Variable readerSecret, operatorSecret -ErrorAction SilentlyContinue
~~~

Điều cần giữ lại là ba câu hỏi độc lập: **endpoint có được bật theo cấu hình không, được công bố qua đâu và yêu cầu nào được phép thực hiện thao tác?** Khi phân tích được cả ba, bạn sẽ biết cần chỉnh cấu hình ở đúng lớp nào.

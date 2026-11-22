# Tách cấu hình quản trị theo môi trường phát triển, kiểm thử và production

## 1. Vì sao không dùng cùng một cấu hình Actuator ở mọi nơi?

Khi phát triển trên máy cá nhân, bạn có thể cần xem danh sách số đo và chi tiết một phép kiểm tra. Khi chạy kiểm thử, bạn cần cấu hình ổn định để xác nhận hành vi. Khi triển khai production, mỗi khả năng quản trị được công bố phải có đối tượng sử dụng và mục đích rõ ràng.

Nếu sao chép nguyên một tệp cấu hình rộng từ máy phát triển sang production, ứng dụng có thể công bố những thông tin mà hệ thống giám sát không cần. Ngược lại, nếu sửa tay cùng một tệp trước mỗi lần triển khai, rất khó biết bản đang chạy đã lấy cấu hình nào.

Cách tổ chức phù hợp là:

~~~text
Cùng mã nguồn và cùng JAR
        +
Cấu hình chung
        +
Phần cấu hình theo môi trường
        +
Giá trị được cung cấp khi chạy
        =
Cấu hình thực tế của tiến trình
~~~

Mục tiêu của bài không phải tạo ba chương trình khác nhau. Bạn sẽ tạo một ứng dụng Spring Boot và dùng ba **Spring profile** để chọn chính sách Actuator.

Ví dụ dùng **Spring Boot 3.3.13**, **Java 21** và **Maven**. Các cổng đều được gắn vào loopback để chạy thử trên cùng máy; cấu hình mang tên `prod` trong bài là mẫu kiểm chứng chính sách, cần được ghép với hệ thống truy cập quản trị thực tế khi triển khai.

## 2. Xác định chính sách trước khi viết YAML

Đừng bắt đầu bằng cách mở toàn bộ endpoint rồi tìm cách đóng bớt. Trước tiên, hãy trả lời:

- Môi trường này cần đọc loại thông tin nào?
- Người chưa xác thực được xem gì?
- Người đã xác thực có cần xem chi tiết health không?
- Công cụ kiểm tra sẽ gọi cổng nào?
- Thông tin đăng nhập được cấp từ đâu?
- Nếu quên chọn môi trường, phạm vi mặc định sẽ ra sao?

Trong bài, chọn chính sách sau:

| Thuộc tính | Chưa chọn profile | `dev` | `test` | `prod` |
| --- | --- | --- | --- | --- |
| Cổng ứng dụng | 18080 | 18080 | 18081 | 18082 |
| Cổng HTTP quản trị | Dùng cổng ứng dụng | Dùng cổng ứng dụng | Dùng cổng ứng dụng | 19082 |
| Endpoint được công bố qua web | health | health, info, metrics | health, info | health |
| Health cho người chưa xác thực | Chỉ trạng thái | Chỉ trạng thái | Chỉ trạng thái | Chỉ trạng thái |
| Chi tiết health cho tài khoản hợp lệ | Không | Có | Không | Không |
| Công bố Actuator qua JMX | Không | Không | Không | Không |
| Nguồn thông tin đăng nhập | Bên ngoài tệp cấu hình | Bên ngoài tệp cấu hình | Bên ngoài tệp cấu hình | Bên ngoài tệp cấu hình |

Đây là quyết định của ví dụ, không phải tập endpoint bắt buộc cho mọi hệ thống. Một production có thể cần xuất số đo cho hệ thống thu thập; khi có yêu cầu đó, hãy bổ sung đúng registry, endpoint hoặc cơ chế xuất tương ứng và kiểm chứng riêng.

Bảng phân biệt **endpoint được công bố** với **quyền sử dụng endpoint**. Hai phần này phải được xem cùng nhau.

## 3. Những lớp cấu hình có trách nhiệm khác nhau

### 3.1. Endpoint được bật

Một endpoint phải có thành phần cần thiết và được bật thì mới có thể được sử dụng. Ví dụ, một endpoint yêu cầu thư viện bổ sung sẽ không xuất hiện chỉ nhờ ghi tên vào YAML.

### 3.2. Endpoint được công bố qua web

`management.endpoints.web.exposure.include` chọn các định danh được công bố qua HTTP. Danh sách này không tự cấp quyền cho người gọi. Nếu có `exclude`, cần xét cả danh sách đó. [Tài liệu endpoint và exposure](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

### 3.3. Quyền truy cập và mức chi tiết

Chặn truy cập một đường dẫn và giảm dữ liệu trả về là hai việc khác nhau. Trong mẫu:

- Health có thể được đọc không cần đăng nhập.
- Các endpoint quản trị khác đang được công bố cần xác thực.
- Riêng `dev` cho người đã xác thực xem thêm chi tiết health.
- `test` và `prod` vẫn trả health gọn ngay cả với tài khoản hợp lệ.

`show-details: never` không thay thế chính sách truy cập. Nó chỉ điều khiển phần dữ liệu health được công bố.

### 3.4. Địa chỉ và cổng

Cổng quản trị riêng giúp tổ chức đường truy cập và kiểm tra. Nó không tự xác thực người gọi. Mạng, cổng và quy tắc ứng dụng cần cùng phù hợp với công cụ vận hành.

Với cổng quản trị riêng, Boot có thuộc tính `management.server.address` để chọn địa chỉ lắng nghe. [ManagementServerProperties](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/web/server/ManagementServerProperties.html).

## 4. Cách tổ chức cấu hình theo Spring profile

Dùng bốn tệp:

~~~text
application.yml
application-dev.yml
application-test.yml
application-prod.yml
~~~

`application.yml` giữ phần chung. Tệp có hậu tố profile cung cấp các giá trị theo môi trường tương ứng. Khi chọn `dev`, cấu hình chung và phần `dev` cùng tham gia; phần theo profile có thể ghi đè giá trị chung. [Spring Boot: Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html).

Ba tên `dev`, `test` và `prod` là quy ước của dự án. Boot không tự phát hiện “đây là production” từ máy chủ rồi chọn `prod` giúp bạn.

Không đặt `spring.profiles.active=dev` làm mặc định trong cấu hình chung của mẫu. Môi trường chạy phải chủ động chọn profile. Nếu chưa chọn, mẫu chỉ công bố health theo phần chung.

Cũng không đặt `spring.profiles.active` bên trong chính `application-prod.yml` để “tự kích hoạt” tệp đó. Việc chọn profile phải xảy ra từ nguồn cấu hình thích hợp, không phụ thuộc vào tệp chỉ được nạp sau khi profile đã được chọn.

### Một môi trường chính cho mỗi lượt chạy

Bài dùng đúng một trong ba profile ở mỗi lượt. Tránh chạy đồng thời `dev,prod` rồi giả định Boot sẽ tự chọn chính sách chặt hơn.

Khi nhiều profile cùng ghi một thuộc tính, kết quả phụ thuộc quy tắc nạp và độ ưu tiên. Không tồn tại nguyên tắc chung “production luôn thắng”. Trong một hệ thống có nhiều profile chức năng, hãy định nghĩa rõ những tổ hợp được phép.

## 5. Ví dụ hoàn chỉnh: một JAR, ba chính sách

### 5.1. Cấu trúc dự án

~~~text
management-profiles/
├── pom.xml
└── src/main/
    ├── java/example/managementprofiles/ManagementProfilesApplication.java
    └── resources/
        ├── application.yml
        ├── application-dev.yml
        ├── application-test.yml
        └── application-prod.yml
~~~

Bạn cần JDK 21, Maven và khả năng tải thư viện trong lần build đầu.

### 5.2. pom.xml

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
    <artifactId>management-profiles</artifactId>
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

Starter Security được thêm để mẫu có cơ chế xác thực khi đọc những endpoint ngoài health. Ví dụ không tự khai báo `SecurityFilterChain`, nên sử dụng chính sách tự cấu hình tương ứng của Boot 3.3.

Khi có Spring Security và chưa định nghĩa chuỗi bảo mật riêng, Boot bảo vệ các actuator ngoài health. Nếu ứng dụng thật đã có chuỗi bảo mật tùy chỉnh, phải kiểm tra quy tắc của chính ứng dụng đó thay vì giả định chính sách mặc định vẫn được giữ. [Bảo mật endpoint Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

### 5.3. Lớp khởi động

Tệp `src/main/java/example/managementprofiles/ManagementProfilesApplication.java`:

~~~java
package example.managementprofiles;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ManagementProfilesApplication {
    public static void main(String[] args) {
        SpringApplication.run(ManagementProfilesApplication.class, args);
    }
}
~~~

Không có mã Java rẽ nhánh theo `dev`, `test` hoặc `prod`. Sự khác nhau của bài nằm ở cấu hình được nạp khi chạy.

### 5.4. Cấu hình chung: application.yml

~~~yaml
spring:
  application:
    name: management-profiles
  jmx:
    enabled: false
  security:
    user:
      name: ${ACTUATOR_USER}
      password: ${ACTUATOR_PASSWORD}

server:
  address: 127.0.0.1
  port: 18080

management:
  endpoints:
    web:
      exposure:
        include:
          - health
    jmx:
      exposure:
        exclude: "*"
  endpoint:
    health:
      show-details: never
      show-components: never
  info:
    env:
      enabled: false
~~~

Phần chung chủ động chọn phạm vi hẹp:

- Chỉ công bố health qua web.
- Không đưa chi tiết và tên thành phần health vào phản hồi.
- Không sử dụng nguồn `info.*` trong phản hồi info theo cấu hình chung.
- Không công bố Actuator qua JMX trong bài.
- Lấy thông tin đăng nhập qua hai biến môi trường.

`ACTUATOR_USER` và `ACTUATOR_PASSWORD` là tên biến do mẫu chọn. Chúng được tham chiếu từ hai thuộc tính của Spring Security, không phải những biến đặc biệt mà Boot tự biết nếu thiếu cấu hình ánh xạ.

Hai giá trị không có mặc định trong YAML. Người chạy phải cung cấp chúng trước khi khởi động. Không dùng một mật khẩu phát triển cố định làm giá trị dự phòng để production vô tình kế thừa.

`spring.jmx.enabled` liên quan tới hỗ trợ JMX do Spring cung cấp; `management.endpoints.jmx.exposure` là phạm vi công bố Actuator qua JMX. Bài ghi rõ cả hai để thể hiện chủ đích không dùng đường quản trị này. [Actuator qua JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

### 5.5. Môi trường phát triển: application-dev.yml

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - metrics
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
  info:
    env:
      enabled: true

info:
  application:
    environment: dev
~~~

`dev` mở thêm info và metrics để thực hành chẩn đoán. Chi tiết health chỉ được đưa cho người được xác định là có quyền xem chi tiết; trong mẫu không đặt danh sách role riêng cho health, nên tài khoản đã xác thực đáp ứng điều kiện mặc định đó.

`show-details` và `show-components` được cấu hình cùng nhau để tránh nhầm giữa nội dung chi tiết và việc xuất hiện danh sách thành phần.

Phần `info.application.environment` chỉ là nhãn do bài tự cung cấp. Nó giúp kiểm chứng tệp cấu hình đang có hiệu lực. Không coi một chuỗi `"dev"` trong JSON là bằng chứng duy nhất về danh sách profile thực sự được kích hoạt.

`management.info.env.enabled=true` bật nguồn đóng góp thông tin từ các thuộc tính bắt đầu bằng `info.`. Nó khác với việc công bố endpoint `env`. [EnvironmentInfoContributor](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/info/EnvironmentInfoContributor.html).

### 5.6. Môi trường kiểm thử: application-test.yml

~~~yaml
server:
  port: 18081

management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
  endpoint:
    health:
      show-details: never
      show-components: never
  info:
    env:
      enabled: true

info:
  application:
    environment: test
~~~

`test` có info để nhận diện lượt chạy, nhưng không công bố metrics trong chính sách của bài. Health giữ dạng gọn cả khi đăng nhập.

Cổng riêng giúp dễ phân biệt lượt kiểm thử với lượt phát triển khi quan sát URL. Điều quan trọng vẫn là kiểm chứng cấu hình, không phải bản thân con số `18081`.

Tên tệp `application-test.yml` không khiến `mvn test` tự kích hoạt Spring profile `test`. Trong kiểm thử có tạo Spring context, có thể chọn profile bằng cơ chế như `@ActiveProfiles("test")`. Việc chạy một JAR ở môi trường kiểm thử cũng cần chọn profile. [Spring TestContext: active profiles](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/env-profiles.html).

### 5.7. Môi trường production: application-prod.yml

~~~yaml
server:
  port: 18082

management:
  server:
    address: 127.0.0.1
    port: 19082
  endpoints:
    web:
      exposure:
        include:
          - health
  endpoint:
    health:
      show-details: never
      show-components: never
  info:
    env:
      enabled: false
~~~

Trong mẫu, ứng dụng dùng cổng `18082`, còn Actuator HTTP chuyển sang `19082`. Công cụ kiểm tra health phải gọi đúng cổng quản trị.

Cả địa chỉ ứng dụng và quản trị đều là loopback trong bài để chạy kiểm chứng cục bộ. Trong một triển khai thật, hãy chọn địa chỉ và tuyến truy cập theo vị trí của agent, proxy hoặc công cụ giám sát.

Chỉ đổi cổng không biến HTTP Basic thành một cơ chế truyền thông tin đăng nhập đã mã hóa. Nếu sử dụng HTTP Basic qua mạng khi triển khai, cần bảo vệ đường truyền bằng TLS và áp dụng cơ chế quản trị phù hợp. Tài khoản đơn trong bộ nhớ của mẫu phục vụ minh họa; thiết kế định danh production thuộc hệ thống thực tế. [Spring Boot và Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html).

Danh sách `include` của từng môi trường được viết đầy đủ để người đọc nhìn thấy chính sách mong muốn. Đừng chỉ thêm một dòng `metrics` vào tệp profile rồi mặc nhiên nghĩ các tên khác sẽ được tự cộng theo ý định của mình.

## 6. Build một lần và cấp thông tin đăng nhập từ bên ngoài

### 6.1. Tạo JAR

Mở PowerShell tại thư mục chứa `pom.xml`:

~~~powershell
java -version
mvn -v
mvn clean package
~~~

Đảm bảo Java mà Maven dùng là JDK 21. Build thành công tạo:

~~~text
target/management-profiles-1.0.0.jar
~~~

Maven đảm nhiệm classpath, biên dịch và đóng gói. Ví dụ cần các thư viện Boot/Actuator/Security, nên một lệnh `javac` trên tệp nguồn mà thiếu classpath sẽ không đủ.

Từ đây, dùng **cùng JAR đó** cho tất cả lượt chạy. Không cần build lại chỉ để thay profile.

### 6.2. Cấp hai biến môi trường trong terminal khởi chạy

Trong Terminal A:

~~~powershell
$env:ACTUATOR_USER = Read-Host "Tên tài khoản quản trị cho bài thực hành"
$enteredSecret = Read-Host "Mật khẩu cho bài thực hành" -AsSecureString
$env:ACTUATOR_PASSWORD = [System.Net.NetworkCredential]::new("", $enteredSecret).Password
~~~

Chọn tài khoản riêng cho bài thực hành. Không in hai biến ra terminal để “kiểm tra đã có chưa”.

Biến môi trường truyền vào tiến trình không làm bí mật biến mất khỏi bộ nhớ; mục đích ở đây là không ghi mật khẩu vào mã nguồn hoặc tệp YAML. Trong môi trường triển khai, dùng cách cấp bí mật do hạ tầng hỗ trợ và giới hạn quyền truy cập nguồn đó.

Một terminal khác không tự nhận những biến vừa đặt trong Terminal A. Với các lệnh cURL cần đăng nhập ở Terminal B, nhập lại **tên tài khoản**:

~~~powershell
$operatorName = Read-Host "Tên tài khoản đã đặt ở Terminal A"
~~~

Các lệnh `curl.exe --user "$operatorName"` bên dưới để cURL hỏi mật khẩu tương tác. Không nối mật khẩu vào lệnh được lưu trong lịch sử shell.

## 7. Chạy và kiểm chứng từng profile

Các lệnh bên dưới dùng Windows PowerShell. `curl.exe` gọi chương trình cURL, tránh alias `curl`. Trên hệ điều hành khác, dùng công cụ tương ứng.

Trước khi chuyển lượt, dừng tiến trình cũ ở Terminal A bằng `Ctrl+C`. Chờ ứng dụng mới hoàn tất khởi động rồi kiểm tra.

### 7.1. Phát triển: dev

Terminal A:

~~~powershell
java -jar target/management-profiles-1.0.0.jar --spring.profiles.active=dev
~~~

Trong nhật ký khởi động, xác nhận profile hoạt động có `dev`. Dòng log chứa thời gian và PID nên không phải stdout cố định để chép nguyên làm kỳ vọng.

Tại Terminal B, health không đăng nhập:

~~~powershell
curl.exe --silent --show-error http://127.0.0.1:18080/actuator/health
~~~

Khi các phép kiểm tra hiện có đều đạt:

~~~json
{"status":"UP"}
~~~

Đọc health bằng tài khoản hợp lệ:

~~~powershell
curl.exe --silent --show-error --user "$operatorName" --header "Accept: application/json" http://127.0.0.1:18080/actuator/health
~~~

Phản hồi có thêm `components` và thông tin health tương ứng. Các giá trị như dung lượng đĩa thay đổi theo máy, nên không nên so khớp toàn bộ JSON với một bộ số cố định.

Kiểm tra info bằng tài khoản hợp lệ:

~~~powershell
curl.exe --silent --show-error --user "$operatorName" --header "Accept: application/json" http://127.0.0.1:18080/actuator/info
~~~

Nội dung JSON của đúng mẫu:

~~~json
{"application":{"environment":"dev"}}
~~~

Kiểm tra mã HTTP của metrics khi đã xác thực:

~~~powershell
curl.exe --silent --show-error --user "$operatorName" --header "Accept: application/json" --output NUL --write-out "%{http_code}" http://127.0.0.1:18080/actuator/metrics
~~~

Kết quả:

~~~text
200
~~~

Nếu gọi info hoặc metrics mà chưa xác thực, với yêu cầu `Accept: application/json` trong mẫu, kết quả là `401`. Endpoint có trong phạm vi công bố không đồng nghĩa bất kỳ người gọi nào cũng được đọc.

### 7.2. Kiểm thử: test

Terminal A:

~~~powershell
java -jar target/management-profiles-1.0.0.jar --spring.profiles.active=test
~~~

Health không đăng nhập:

~~~powershell
curl.exe --silent --show-error http://127.0.0.1:18081/actuator/health
~~~

Kết quả khi đạt:

~~~json
{"status":"UP"}
~~~

Health khi đã xác thực vẫn giữ dạng gọn, vì profile này chọn `never` cho cả chi tiết và thành phần.

Info với tài khoản hợp lệ:

~~~powershell
curl.exe --silent --show-error --user "$operatorName" --header "Accept: application/json" http://127.0.0.1:18081/actuator/info
~~~

Nội dung JSON:

~~~json
{"application":{"environment":"test"}}
~~~

Metrics với tài khoản hợp lệ:

~~~powershell
curl.exe --silent --show-error --user "$operatorName" --header "Accept: application/json" --output NUL --write-out "%{http_code}" http://127.0.0.1:18081/actuator/metrics
~~~

Kết quả:

~~~text
404
~~~

Việc kiểm tra bằng tài khoản hợp lệ giúp tránh nhầm `401` ở lớp xác thực với việc endpoint không được công bố.

### 7.3. Production: prod

Terminal A:

~~~powershell
java -jar target/management-profiles-1.0.0.jar --spring.profiles.active=prod
~~~

Health cần được gọi ở **19082**:

~~~powershell
curl.exe --silent --show-error http://127.0.0.1:19082/actuator/health
~~~

Kết quả khi đạt:

~~~json
{"status":"UP"}
~~~

Ngay cả tài khoản hợp lệ cũng không được mẫu trả chi tiết health trong profile này.

Kiểm tra metrics trên đúng cổng quản trị, có xác thực:

~~~powershell
curl.exe --silent --show-error --user "$operatorName" --header "Accept: application/json" --output NUL --write-out "%{http_code}" http://127.0.0.1:19082/actuator/metrics
~~~

Kết quả:

~~~text
404
~~~

Info cũng không được công bố trong profile `prod`. Đối với đúng mẫu, gọi `/actuator/health` trên cổng ứng dụng `18082` bằng tài khoản hợp lệ trả `404`: endpoint quản trị đã chuyển sang cổng riêng.

Đừng lấy phản hồi trên cổng cũ làm bằng chứng về profile mới. Một tiến trình khác vẫn có thể đang lắng nghe ở cổng mà bạn quên thay.

### 7.4. Chưa chọn profile

Dừng tiến trình rồi chạy:

~~~powershell
java -jar target/management-profiles-1.0.0.jar
~~~

Khi không có nguồn cấu hình khác kích hoạt profile, mẫu dùng chính sách chung: health trên `18080`, không chi tiết; info và metrics không được công bố.

Đây là lựa chọn mặc định hạn chế của bài. Nó không chứng minh bạn đã triển khai đúng production. Hệ thống triển khai vẫn cần xác nhận profile dự kiến được chọn.

### 7.5. Dọn biến của terminal thực hành

Sau khi dừng mọi lượt chạy, có thể xóa các biến khỏi terminal đã cấp chúng:

~~~powershell
Remove-Item Env:ACTUATOR_USER, Env:ACTUATOR_PASSWORD -ErrorAction SilentlyContinue
Remove-Variable enteredSecret -ErrorAction SilentlyContinue
~~~

Thao tác này bỏ các tham chiếu/biến của phiên shell, không phải bảo đảm xóa sạch mọi bản sao khỏi bộ nhớ. Không xóa hoặc đổi các biến cùng tên của một tiến trình triển khai đang được sử dụng.

## 8. Chọn profile và cấp cấu hình từ môi trường chạy

Trong các lệnh thực hành, profile được truyền qua tham số sau tên JAR:

~~~powershell
java -jar target/management-profiles-1.0.0.jar --spring.profiles.active=prod
~~~

Một cách khác là để hệ thống khởi chạy cung cấp biến `SPRING_PROFILES_ACTIVE`:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar target/management-profiles-1.0.0.jar
~~~

Chọn một cách rõ ràng cho môi trường triển khai, đừng để nhiều nơi cùng đặt các giá trị trái nhau.

Sau khi thử bằng biến môi trường trong terminal cục bộ, bỏ nó nếu không muốn ảnh hưởng lượt chạy tiếp:

~~~powershell
Remove-Item Env:SPRING_PROFILES_ACTIVE -ErrorAction SilentlyContinue
~~~

`-Pprod` của Maven là cơ chế profile của công cụ build, không phải lệnh thay thế `--spring.profiles.active=prod`. Tương tự, chạy một bước có tên “test” trong CI không tự chọn `application-test.yml`.

Thay đổi tệp YAML đã đóng gói trong mã nguồn đòi hỏi build lại JAR để chứa thay đổi. Chỉ chọn một profile khác đã có trong JAR thì không cần build lại. Với mẫu thông thường này, sửa tệp sau khi tiến trình đã khởi động cũng không tự làm cấu hình đang chạy đổi ngay.

## 9. Thứ tự ghi đè: kiểm tra giá trị thực tế, không chỉ tên tệp

Một giá trị trong `application-prod.yml` không phải khóa bất biến. Cấu hình từ bên ngoài hoặc tham số chạy có thể làm giá trị hiệu lực khác đi.

Trong lượt chạy JAR thông thường của bài, có thể ghi nhớ chuỗi rút gọn:

~~~text
Tệp cấu hình trong JAR
    -> tệp cấu hình ngoài JAR
    -> biến môi trường
    -> thuộc tính hệ thống Java
    -> tham số dòng lệnh
~~~

Nguồn có độ ưu tiên cao hơn có thể ghi đè nguồn trước. Đây là mô hình rút gọn; môi trường test và các nguồn chuyên biệt còn có quy tắc riêng. [Thứ tự nguồn cấu hình của Boot](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

Ví dụ, đặt profile `prod` nhưng truyền thêm một danh sách exposure khác có thể làm chính sách thực tế không còn giống bảng ở đầu bài. Vì vậy, tên profile không thay thế kiểm tra HTTP sau khi khởi động.

Cần phân biệt cú pháp:

~~~text
-Dthuoc.tinh=giaTri      đứng trước -jar: thuộc tính hệ thống Java
--thuoc.tinh=giaTri     đứng sau tên JAR: tham số của ứng dụng
~~~

Hai dòng trên mô tả hình thức cú pháp, không phải lệnh chạy của mẫu.

Đối với cấu hình vận hành cấp bên ngoài:

- Ghi nhận rõ nguồn nào sở hữu profile, cổng và phạm vi exposure.
- Hạn chế các giá trị trùng nhau ở nhiều nơi.
- Không in toàn bộ môi trường hoặc cấu hình chỉ để tìm một thuộc tính.
- Xác minh các giá trị cần thiết bằng phép kiểm tra hẹp.

Nếu bổ sung thư mục cấu hình, cần hiểu sự khác nhau giữa `spring.config.location` thay thế các vị trí mặc định và `spring.config.additional-location` bổ sung vị trí. Không thêm một vị trí tùy ý rồi giả định toàn bộ cấu hình đóng gói vẫn được nạp theo cách cũ.

## 10. Kiểm thử chính sách bằng hành vi quan sát được

Một bài kiểm tra có giá trị cần xác nhận cả thứ **được phép có** lẫn thứ **không được công bố**.

Với mẫu này:

| Lượt chạy | Kiểm tra chính |
| --- | --- |
| dev | Health công khai gọn; health có xác thực có thành phần; info đúng nhãn; metrics có xác thực trả 200 |
| test | Health luôn gọn; info đúng nhãn; metrics có xác thực trả 404 |
| prod | Health ở cổng 19082; không chi tiết; info/metrics có xác thực trả 404 |
| Không profile | Không vô tình nhận chính sách rộng của dev |

Khi so sánh:

- So phần dữ liệu có ý nghĩa, không cố định dung lượng đĩa hoặc thời gian trong health.
- Dùng danh tính đúng cho phép kiểm tra endpoint bị hạn chế.
- Xác minh cổng thực tế; nếu dùng cổng ngẫu nhiên trong kiểm thử, lấy cổng từ server đã khởi động.
- Dùng bí mật tạm cho môi trường kiểm thử, không lấy tài khoản production.
- Kiểm tra cả nguồn cấu hình bên ngoài mà bước triển khai thực sự sử dụng.

Một context test chỉ chạy trong bộ nhớ chưa tự chứng minh cổng quản trị riêng đã được mở và routing đúng. Khi cổng riêng là một phần hợp đồng, cần phép kiểm tra với máy chủ thật.

Bản mẫu đã được thiết kế để có thể kiểm tra cùng một JAR theo bốn lượt trên. Trong dự án của bạn, hãy kiểm tra kết quả sau cùng của triển khai, thay vì chỉ tìm thấy một tệp có tên `application-prod.yml`.

## 11. Những lỗi cấu hình thường gặp

### Lấy cấu hình dev làm phần chung

Nếu đặt danh sách rộng trong `application.yml` rồi trông chờ mọi môi trường đều nhớ đóng lại, một lượt chạy quên profile có thể kế thừa phạm vi không mong muốn.

Hãy giữ phần chung phù hợp với lựa chọn mặc định của dự án; phần mở rộng cho chẩn đoán đặt ở môi trường cần nó.

### Chỉ thêm tên endpoint mà quên danh sách hiệu lực

Khi ghi cấu hình theo nhiều nguồn, đừng tự suy đoán chúng sẽ cộng dồn theo ý định. Đặt đầy đủ danh sách mong muốn ở lớp sở hữu chính sách rồi kiểm tra các URL.

Nếu có cả include và exclude, phải kiểm tra cả hai; một tên trong include có thể vẫn bị loại bởi exclude.

### Nhầm “đã xác thực” với “được xem mọi dữ liệu”

Mẫu cho người đã xác thực xem chi tiết health chỉ ở dev. Test và prod vẫn chọn không trả chi tiết. Xác thực thành công không làm mọi giới hạn cấu hình mất tác dụng.

### Tưởng tách cổng là đã hoàn thành bảo mật

Cổng riêng xác định đường truy cập. Còn phải xét ai có thể kết nối và danh tính nào được sử dụng chức năng quản trị.

### Cấu hình test làm lệch kết quả về production

Nếu test luôn ghi đè exposure thành một danh sách rộng hoặc tắt bảo mật, nó có thể không phát hiện lỗi chính sách triển khai. Khi mục tiêu là kiểm tra prod, hãy chạy với cấu hình prod và chỉ thay những giá trị cần cho hạ tầng kiểm thử.

### Nghĩ tên profile là bằng chứng duy nhất

Nhãn `info.application.environment` do người viết cấu hình cấp; tham số chạy cũng có thể ghi đè những thuộc tính khác. Cần đối chiếu profile, nguồn cấu hình và kết quả HTTP.

### Kế thừa biến môi trường từ terminal cũ

Một biến `SPRING_PROFILES_ACTIVE` còn trong phiên shell có thể khiến lệnh “không truyền profile” vẫn chạy với profile đã đặt. Kiểm tra cách tiến trình được khởi chạy trước khi kết luận Boot bỏ qua tệp chung.

## 12. Bài tập tự kiểm tra

**Bài 1 — Bỏ profile khi khởi động.**

Sau khi đã xóa biến `SPRING_PROFILES_ACTIVE` của terminal thực hành, chạy JAR không có `--spring.profiles.active`. Dự đoán health, info và metrics rồi kiểm chứng với đúng tài khoản.

Kết quả cần giải thích: không chọn profile trong mẫu không tự kích hoạt dev hay prod; cấu hình chung có chính sách riêng.

**Bài 2 — Đổi vị trí công cụ giám sát.**

Một agent chuyển sang máy khác nhưng endpoint quản trị vẫn bind `127.0.0.1`. Vì sao agent không kết nối được?

Cần xét địa chỉ lắng nghe và tuyến kết nối. Mở thêm tên endpoint không giải quyết được một đường mạng chưa tồn tại.

**Bài 3 — Kiểm tra 401 và 404.**

Ở profile test, gọi info không có tài khoản, rồi gọi metrics với tài khoản hợp lệ. Giải thích vì sao hai mã khác nhau dù cả hai lượt đều không trả dữ liệu bạn đang tìm.

Trong mẫu, info được công bố nhưng yêu cầu xác thực; metrics không được công bố cho profile này. Thứ tự xử lý có thể che khuất lỗi định tuyến nếu bạn chưa qua lớp xác thực.

**Bài 4 — Cùng JAR nhưng khác chính sách thực tế.**

Hai tiến trình dùng cùng JAR và cùng tên profile, nhưng một bên có thêm biến môi trường ghi đè exposure. Chúng có bắt buộc trả cùng kết quả quản trị không?

Không. Phải xét toàn bộ nguồn cấu hình hiệu lực. Tính nhất quán của sản phẩm build là điều cần thiết, còn cấu hình chạy vẫn cần được kiểm chứng.

Điểm cốt lõi của việc tách môi trường là **viết rõ chính sách, chọn đúng lớp cấu hình và xác minh kết quả thực tế**. Profile giúp tổ chức cấu hình; trách nhiệm vận hành còn bao gồm cách cấp giá trị và cách kiểm tra tiến trình đã dùng chúng.
